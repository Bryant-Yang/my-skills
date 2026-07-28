#!/usr/bin/env python3
"""One-shot, dependency-free client for Kimi Code's ACP server."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any


class AcpError(RuntimeError):
    pass


class BoundedText:
    def __init__(self, limit: int = 4096) -> None:
        self.limit = limit
        self.head = ""
        self.tail = ""
        self.total = 0

    def append(self, text: str) -> None:
        self.total += len(text)
        if len(self.head) < self.limit:
            take = self.limit - len(self.head)
            self.head += text[:take]
            text = text[take:]
        if text:
            self.tail = (self.tail + text)[-self.limit :]

    def render(self) -> str:
        if not self.tail:
            return self.head
        omitted = self.total - len(self.head) - len(self.tail)
        if omitted > 0:
            return f"{self.head}\n... omitted {omitted} chars ...\n{self.tail}"
        return self.head + self.tail


async def read_json_lines(
    stream: asyncio.StreamReader,
) -> AsyncIterator[bytes]:
    """Read newline frames without StreamReader.readline's 64 KiB limit."""
    buffer = b""
    while chunk := await stream.read(65536):
        buffer += chunk
        while b"\n" in buffer:
            raw, buffer = buffer.split(b"\n", 1)
            if raw.strip():
                yield raw
    if buffer.strip():
        yield buffer


class AcpClient:
    def __init__(
        self,
        command: list[str],
        cwd: str,
        permission: str,
        on_notification: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self.command = command
        self.cwd = cwd
        self.permission = permission
        self.on_notification = on_notification
        self.display_updates = False
        self.proc: asyncio.subprocess.Process | None = None
        self.reader_task: asyncio.Task[None] | None = None
        self.stderr_task: asyncio.Task[None] | None = None
        self.pending: dict[int, asyncio.Future[Any]] = {}
        self.next_id = 0
        self.write_lock = asyncio.Lock()
        self.stderr = BoundedText()
        self.protocol_version: int | None = None
        self.agent_info: dict[str, Any] = {}

    async def start(self) -> None:
        if self.proc is not None and self.proc.returncode is None:
            raise AcpError("ACP client is already running")
        self.proc = await asyncio.create_subprocess_exec(
            *self.command,
            cwd=self.cwd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        self.reader_task = asyncio.create_task(self._read_loop())
        self.stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            result = await self.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {
                            "readTextFile": False,
                            "writeTextFile": False,
                        },
                        "terminal": False,
                    },
                    "clientInfo": {
                        "name": "kimi-acp-communication-skill",
                        "version": "1.0.0",
                    },
                },
                timeout=10,
            )
        except BaseException:
            await self.close()
            raise
        self.protocol_version = result.get("protocolVersion")
        self.agent_info = result.get("agentInfo", {})
        if self.protocol_version != 1:
            await self.close()
            raise AcpError(
                f"unsupported ACP protocol version: {self.protocol_version!r}"
            )

    async def close(self) -> None:
        for task in (self.reader_task, self.stderr_task):
            if task is not None:
                task.cancel()

        if self.proc is not None and self.proc.returncode is None:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except TimeoutError:
                try:
                    os.killpg(self.proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await self.proc.wait()

        for task in (self.reader_task, self.stderr_task):
            if task is not None:
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        request_id = self.next_id
        self.next_id += 1
        future = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params or {},
                }
            )
            if timeout is not None:
                return await asyncio.wait_for(future, timeout)
            return await future
        finally:
            self.pending.pop(request_id, None)

    async def list_sessions(self) -> list[dict[str, Any]]:
        result = await self.request("session/list", {})
        return result.get("sessions", [])

    async def new_session(self, cwd: str) -> str:
        result = await self.request(
            "session/new", {"cwd": cwd, "mcpServers": []}
        )
        return result["sessionId"]

    async def load_session(self, session_id: str, cwd: str) -> None:
        self.display_updates = False
        await self.request(
            "session/load",
            {
                "sessionId": session_id,
                "cwd": cwd,
                "mcpServers": [],
            },
        )

    async def prompt(self, session_id: str, text: str) -> dict[str, Any]:
        self.display_updates = True
        return await self.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": text}],
            },
        )

    async def cancel(self, session_id: str) -> None:
        await self._send(
            {
                "jsonrpc": "2.0",
                "method": "session/cancel",
                "params": {"sessionId": session_id},
            }
        )

    async def _send(self, message: dict[str, Any]) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise AcpError("ACP process is not running")
        data = json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"
        async with self.write_lock:
            self.proc.stdin.write(data)
            await self.proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        try:
            async for chunk in read_json_lines(self.proc.stdout):
                try:
                    message = json.loads(chunk)
                except json.JSONDecodeError:
                    continue

                if "method" in message and "id" in message:
                    await self._handle_reverse_request(message)
                elif "method" in message:
                    if self.display_updates and self.on_notification is not None:
                        self.on_notification(
                            message["method"], message.get("params", {})
                        )
                else:
                    future = self.pending.get(message.get("id"))
                    if future is None or future.done():
                        continue
                    if "error" in message:
                        error = message["error"]
                        future.set_exception(
                            AcpError(
                                f"{error.get('code')}: {error.get('message')}"
                            )
                        )
                    else:
                        future.set_result(message.get("result", {}))
        finally:
            detail = self.stderr.render().strip()
            reason = "Kimi ACP process disconnected"
            if detail:
                reason += f": {detail[-500:]}"
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(AcpError(reason))

    async def _handle_reverse_request(self, message: dict[str, Any]) -> None:
        request_id = message["id"]
        if message["method"] != "session/request_permission":
            await self._send(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "method not found",
                    },
                }
            )
            return

        params = message.get("params", {})
        outcome: dict[str, Any] = {"outcome": "cancelled"}
        if self.permission == "auto":
            options = params.get("options", [])
            selected = next(
                (
                    option
                    for option in options
                    if option.get("kind") == "allow_once"
                ),
                None,
            )
            if selected is None:
                selected = next(
                    (
                        option
                        for option in options
                        if str(option.get("kind", "")).startswith("allow")
                    ),
                    None,
                )
            if selected is not None and selected.get("optionId"):
                outcome = {
                    "outcome": "selected",
                    "optionId": selected["optionId"],
                }

        await self._send(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"outcome": outcome},
            }
        )

    async def _drain_stderr(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        while chunk := await self.proc.stderr.read(8192):
            self.stderr.append(chunk.decode("utf-8", errors="replace"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List or prompt Kimi Code sessions through ACP."
    )
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--list-sessions",
        action="store_true",
        help="List sessions visible to kimi acp.",
    )
    action.add_argument(
        "--new-session",
        action="store_true",
        help="Create an exclusively owned session before prompting.",
    )
    action.add_argument(
        "--session",
        metavar="ID",
        help="Load and prompt an existing session.",
    )
    prompt = parser.add_mutually_exclusive_group()
    prompt.add_argument("--prompt", help="Prompt text.")
    prompt.add_argument(
        "--prompt-file",
        type=Path,
        help="UTF-8 file containing the prompt.",
    )
    parser.add_argument(
        "--cwd",
        default=os.getcwd(),
        help="Workspace directory passed to Kimi (default: current directory).",
    )
    parser.add_argument(
        "--cwd-only",
        action="store_true",
        help="With --list-sessions, show only sessions whose cwd matches --cwd.",
    )
    parser.add_argument(
        "--permission",
        choices=("deny", "auto"),
        default="deny",
        help="Permission policy; auto must be explicitly authorized.",
    )
    parser.add_argument(
        "--acknowledge-session-owner",
        action="store_true",
        help="Acknowledge that no other writer owns the loaded session, or that "
        "the user explicitly accepted the concurrent-writer risk.",
    )
    parser.add_argument(
        "--kimi-bin",
        default="kimi",
        help="Path or command name for the Kimi CLI.",
    )
    return parser


def read_prompt(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.list_sessions:
        if args.prompt or args.prompt_file:
            parser.error("--list-sessions cannot be combined with a prompt")
        return ""
    if args.prompt is None and args.prompt_file is None:
        parser.error("--prompt or --prompt-file is required when prompting")
    if args.prompt_file is not None:
        return args.prompt_file.read_text(encoding="utf-8")
    return args.prompt


class StreamPrinter:
    def __init__(self) -> None:
        self.tool_calls: set[str] = set()

    def __call__(self, method: str, params: dict[str, Any]) -> None:
        if method != "session/update":
            return
        update = params.get("update", {})
        kind = update.get("sessionUpdate")
        if kind == "agent_message_chunk":
            text = update.get("content", {}).get("text", "")
            if text:
                print(text, end="", flush=True)
        elif kind == "tool_call":
            key = str(
                update.get("toolCallId")
                or update.get("id")
                or update.get("title")
                or len(self.tool_calls)
            )
            if key not in self.tool_calls:
                self.tool_calls.add(key)
                title = update.get("title", "tool call")
                print(f"\n[kimi tool] {title}", file=sys.stderr, flush=True)


async def run(args: argparse.Namespace, prompt: str) -> int:
    cwd = str(Path(args.cwd).expanduser().resolve())
    if not Path(cwd).is_dir():
        raise AcpError(f"working directory does not exist: {cwd}")
    if args.session and not args.acknowledge_session_owner:
        raise AcpError(
            "loading an existing session requires "
            "--acknowledge-session-owner"
        )

    printer = StreamPrinter()
    client = AcpClient(
        [args.kimi_bin, "acp"],
        cwd=cwd,
        permission=args.permission,
        on_notification=printer,
    )
    session_id: str | None = None
    try:
        await client.start()
        print(
            f"[acp] protocol={client.protocol_version} "
            f"agent={client.agent_info.get('name', 'kimi')}",
            file=sys.stderr,
        )
        if args.list_sessions:
            sessions = await client.list_sessions()
            if args.cwd_only:
                sessions = [
                    session
                    for session in sessions
                    if session.get("cwd")
                    and str(Path(session["cwd"]).expanduser().resolve()) == cwd
                ]
            print(json.dumps(sessions, ensure_ascii=False, indent=2))
            return 0

        if args.new_session:
            session_id = await client.new_session(cwd)
            print(f"[acp] new session={session_id}", file=sys.stderr)
        else:
            session_id = args.session
            assert session_id is not None
            await client.load_session(session_id, cwd)
            print(f"[acp] loaded session={session_id}", file=sys.stderr)

        try:
            result = await client.prompt(session_id, prompt)
        except asyncio.CancelledError:
            await client.cancel(session_id)
            raise
        if not prompt.endswith("\n"):
            print()
        print(
            f"[acp] session={session_id} "
            f"stopReason={result.get('stopReason', '')}",
            file=sys.stderr,
        )
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        prompt = read_prompt(args, parser)
        return asyncio.run(run(args, prompt))
    except KeyboardInterrupt:
        return 130
    except (AcpError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
