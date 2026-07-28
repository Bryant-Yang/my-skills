# Kimi ACP protocol notes

These notes record behavior verified locally on 2026-07-26 with Kimi Code CLI
0.29.1. Re-run the handshake after upgrades because optional capabilities and
event shapes may evolve.

## Observed lifecycle

ACP uses newline-delimited JSON-RPC 2.0 over stdio:

```text
client                         kimi acp
  |--- initialize ------------->|
  |<-- protocolVersion=1 --------|
  |--- session/list ------------>|
  |<-- sessions -----------------|
  |--- session/load or new ----->|
  |<-- result --------------------|
  |--- session/prompt ---------->|
  |<-- session/update -----------|  repeated
  |<-- stopReason=end_turn -------|
```

The locally observed initialization request:

```json
{
  "jsonrpc": "2.0",
  "id": 0,
  "method": "initialize",
  "params": {
    "protocolVersion": 1,
    "clientCapabilities": {
      "fs": {
        "readTextFile": false,
        "writeTextFile": false
      },
      "terminal": false
    }
  }
}
```

Session load:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "session/load",
  "params": {
    "sessionId": "session_xxx",
    "cwd": "/path/to/workspace",
    "mcpServers": []
  }
}
```

Prompt:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "session/prompt",
  "params": {
    "sessionId": "session_xxx",
    "prompt": [
      {
        "type": "text",
        "text": "message"
      }
    ]
  }
}
```

## Session update handling

Important `sessionUpdate` values include:

- `agent_message_chunk`: new assistant text.
- `agent_thought_chunk`: internal progress; do not expose raw chain of thought.
- `tool_call`: a tool started; show a concise status once.
- `tool_call_update`: repeated progress updates; deduplicate or summarize.

`session/load` can replay historical updates. Keep display disabled until the
load response completes, then enable it immediately before `session/prompt`.

## Completion and interrupted turns

The authoritative completion signal is the response to `session/prompt`,
including its `stopReason`. `tool_call` events and streamed text are progress
only. Kimi can be silent after an edit while the next `llm.request` is still in
flight.

When a command transport appears to finish early:

1. Check whether the exact ACP helper PID is still alive. If it is, do not open
   another writer for that session.
2. If the helper exited without returning a prompt result, inspect
   `agents/main/wire.jsonl`.
3. A wire tail ending in `llm.request` or `step.begin` is an interrupted turn.
   Inspect the workspace for already-applied tool edits, then resume the same
   session with a prompt that starts from current file state.
4. Prefer a PTY or resumable command session for long modification turns so
   stdout/stderr and process lifetime stay attached until `stopReason`.

## Permission requests

Kimi can send a reverse JSON-RPC request:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "method": "session/request_permission",
  "params": {
    "options": [
      {
        "optionId": "allow",
        "kind": "allow_once"
      }
    ]
  }
}
```

Default deny response:

```json
{
  "jsonrpc": "2.0",
  "id": 17,
  "result": {
    "outcome": {
      "outcome": "cancelled"
    }
  }
}
```

Explicit auto mode selects `allow_once` first, then another `allow*` option.
If no allow option exists, return cancelled.

## Cancellation

Cancellation is a notification:

```json
{
  "jsonrpc": "2.0",
  "method": "session/cancel",
  "params": {
    "sessionId": "session_xxx"
  }
}
```

After sending it, wait for the original `session/prompt` to finish with a
cancelled stop reason. Do not begin a second prompt on the same session before
the first prompt has stopped. If the agent does not confirm cancellation within
a finite timeout, close the process and treat the connection as unusable.

## Native TUI limitation

The native `kimi` command and `kimi acp` are alternative frontends around Kimi
Code sessions. Starting an independent ACP server and loading a session does not
attach to the already-running native TUI's event loop.

Truth table:

| Action | Kimi agent receives it | Existing native TUI live-updates |
|---|---:|---:|
| Type in native TUI | yes | yes |
| Send through the TUI's own ACP client | yes | yes |
| Independent `kimi acp` loads same session | yes | no guarantee |
| Reopen with `kimi -S session_xxx` | history is loaded | yes, after reopen |

For a live shared UI, one frontend must own the ACP connection and route all
human and external messages through the same queue.
