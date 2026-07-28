---
name: kimi-acp-communication
description: Safely inspect, load, and communicate with Kimi Code sessions through `kimi acp`, including sending reviews or follow-up tasks, streaming Kimi's response, handling permissions, and explaining why an already-open native Kimi TUI will not live-refresh. Use this skill whenever the user asks to send something to Kimi, continue or inspect a Kimi session, communicate with a Kimi TUI through a protocol, automate `kimi acp`, verify that Kimi received a message, or says phrases such as "发给 Kimi", "给 Kimi TUI 发消息", "继续 Kimi 会话", or "通过 ACP 跟 Kimi 通信".
compatibility: macOS or Linux, Python 3.11+, and a locally installed `kimi` CLI with the `acp` command
---

# Kimi ACP Communication

Use ACP when the goal is to communicate with the Kimi agent through a structured
protocol. Do not inject keystrokes into a terminal unless the user explicitly
requests terminal automation.

This skill covers Kimi's **Agent Client Protocol** implementation. It is not the
retired IBM Agent Communication Protocol that merged into A2A.

## Core truth

Keep these two outcomes separate:

- Sending `session/prompt` through `kimi acp` lets the Kimi **agent** receive and
  execute the message.
- An already-open native `kimi` TUI does not subscribe to events from an
  independent `kimi acp` process, so its screen does not reliably live-refresh.

Loading the same persisted session proves shared history, not shared live UI.
Never promise that the existing native TUI will update immediately.

## Safety contract

1. Treat one ACP client as the sole writer for a session while it is active.
   Concurrently writing the same session from a native Kimi TUI and a separate
   ACP process can race or fork the user's mental model of the conversation.
2. Default permission handling to `deny`. Use `auto` only when the user clearly
   authorized Kimi to modify files or execute tools.
3. Resolve the exact session ID and working directory before sending.
4. Suppress historical `session/update` notifications emitted during
   `session/load`; stream only the new prompt's events.
5. Close the ACP subprocess after a one-shot operation and verify that no
   `kimi acp` process remains.
6. Report what was sent, the target session, Kimi's stop reason, changes or
   tests Kimi reported, and any visibility limitation.
7. Treat the `session/prompt` response as the completion signal. Tool-call
   output, a quiet stdout period, or a command wrapper returning partial output
   does not prove that the turn finished.

## Workflow

### 1. Inspect local state

Run:

```bash
command -v kimi
kimi --version
kimi --help
ps -axo pid,ppid,tty,stat,command | rg '[k]imi acp|[k]imi$'
```

Confirm that `kimi acp` exists. A raw `kimi` process attached to a TTY is the
native TUI; a `kimi acp` process is an ACP server.

### 2. Resolve the session

Prefer a session ID explicitly supplied by the user or already established in
the current conversation. Otherwise list sessions:

```bash
python scripts/kimi_acp.py \
  --list-sessions \
  --cwd /path/to/workspace \
  --cwd-only
```

Do not guess when multiple plausible sessions exist. Ask the user only when the
target cannot be determined from the working directory, recency, or prior
context.

Kimi persists sessions under `~/.kimi-code/sessions/`. Reading those files may
help verify that a message was persisted, but do not edit them.

### 3. Check session ownership

Before loading an existing session, determine whether a native Kimi TUI may
still be using it.

- If no other writer is active, proceed.
- If a native TUI is active, explain that ACP can make the agent act but cannot
  live-update that TUI. Prefer asking the user to close/relinquish the native
  TUI before writing.
- Proceed concurrently only when the user explicitly accepts the risk. The
  helper requires `--acknowledge-session-owner` as a deliberate acknowledgement.

### 4. Choose permission mode

For review, explanation, or read-only inspection:

```bash
--permission deny
```

For an explicitly authorized modification:

```bash
--permission auto
```

Never infer `auto` merely because the message mentions code.

### 5. Send the message

Use a prompt file for long reviews to avoid shell quoting problems:

```bash
python scripts/kimi_acp.py \
  --session session_xxx \
  --acknowledge-session-owner \
  --cwd /path/to/workspace \
  --permission deny \
  --prompt-file /tmp/kimi-review.md
```

For a new, exclusively owned session:

```bash
python scripts/kimi_acp.py \
  --new-session \
  --cwd /path/to/workspace \
  --permission auto \
  --prompt "Implement the approved change and run the relevant tests."
```

The script writes Kimi's new text to stdout and protocol/status information to
stderr. It performs `initialize`, then `session/load` or `session/new`, followed
by `session/prompt`.

For long modification turns, keep the process attached to a PTY or another
resumable command session. A successful turn ends with a line like:

```text
[acp] session=session_xxx stopReason=end_turn
```

Kimi may emit several tool calls and then stay textually quiet while another
model step is running. Do not start a second writer merely because output is
quiet. Check the exact helper PID first. If the command channel detaches while
the helper is still alive, continue monitoring that process; if the helper has
exited without a terminal `stopReason`, inspect the session wire log and the
workspace before resuming the same session from its current state.

### 6. Verify independently

Do not rely only on Kimi's final statement.

- Inspect the files Kimi says it changed.
- Run relevant tests or read-only checks.
- Confirm no helper process remains:

```bash
ps -axo pid,ppid,tty,stat,command | rg '[k]imi acp'
```

For persistence evidence, inspect the target session's `wire.jsonl` or
`state.json` read-only and search for a distinctive phrase from the prompt.
The agent wire log is normally under
`<session-dir>/agents/main/wire.jsonl`. A tail ending at `llm.request` or
`step.begin` without a terminal turn result is evidence of an interrupted turn,
not successful completion. Preserve already-applied edits, then send a concise
continuation prompt that tells Kimi to inspect the current file state and finish
the remaining work.

### 7. Explain how the user can view history

If the native TUI did not update, tell the user to reopen the exact session:

```bash
kimi -S session_xxx
```

This reloads persisted history; it does not turn the native TUI into a live ACP
subscriber.

## Reporting format

Lead with the result:

```text
已通过 ACP 发给 Kimi，目标 session 为 <id>，Kimi 以 <stopReason> 结束。
独立验证：<tests/checks>.
当前原生 Kimi TUI 不会实时刷新；需要重新加载该 session 才能看到历史。
```

If the operation was not performed because another writer owns the session,
state that plainly and give the safest next action.

## Reference

Read [references/protocol-notes.md](references/protocol-notes.md) when debugging
handshake shapes, permission responses, event types, cancellation, or TUI
visibility.
