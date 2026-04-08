#!/usr/bin/env python3
"""Run Claude CLI with a PTY and write raw stream-json lines to a file.

Usage: scholar-runner.py --stream-file FILE [--session-file FILE] [--] CLAUDE_ARGS...

Unlike claude-pty.py (which formats output for terminal display), this script
writes the RAW stream-json lines to the stream file for backend SSE parsing.
It also displays human-readable progress to stderr for debugging.
"""
import json
import os
import pty
import select
import subprocess
import sys
import termios
import time
from datetime import datetime


def _ts():
    return datetime.now().strftime("%H:%M:%S")


_DIM = "\033[2m"
_RESET = "\033[0m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"


def main():
    args = sys.argv[1:]
    stream_file = None
    session_file = None
    prompt_file = None

    if "--stream-file" in args:
        idx = args.index("--stream-file")
        stream_file = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--session-file" in args:
        idx = args.index("--session-file")
        session_file = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--prompt-file" in args:
        idx = args.index("--prompt-file")
        prompt_file = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--" in args:
        args.remove("--")

    if not args or not stream_file:
        print("Usage: scholar-runner.py --stream-file FILE [--session-file FILE] [--prompt-file FILE] [--] CLAUDE_ARGS...",
              file=sys.stderr)
        sys.exit(1)

    # Read prompt from file if provided (avoids execve ARG_MAX limits).
    # Claude CLI reads the prompt from stdin when piped with -p flag.
    prompt_data = None
    if prompt_file:
        with open(prompt_file, "rb") as pf:
            raw = pf.read()
        prompt_data = raw.decode("utf-8", errors="replace")

    # Create pty pair
    master_fd, slave_fd = pty.openpty()

    # Disable output post-processing
    attrs = termios.tcgetattr(slave_fd)
    attrs[1] = attrs[1] & ~termios.OPOST
    termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

    proc = subprocess.Popen(
        args,
        stdin=subprocess.PIPE if prompt_data else subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )

    # Pipe prompt via stdin to avoid argument length limits
    if prompt_data and proc.stdin:
        proc.stdin.write(prompt_data.encode("utf-8"))
        proc.stdin.close()

    os.close(slave_fd)

    line_buffer = b""
    session_id = None
    sf = open(stream_file, "wb")  # binary mode for precise byte control

    def process_data(data):
        nonlocal line_buffer, session_id

        line_buffer += data
        while b"\n" in line_buffer:
            line, line_buffer = line_buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            # Write raw JSON line to stream file
            sf.write(text.encode("utf-8") + b"\n")
            sf.flush()

            # Parse for session ID and display
            try:
                event = json.loads(text)
                etype = event.get("type", "")

                # Extract session ID
                if session_id is None:
                    sid = event.get("sessionId") or event.get("session_id")
                    if sid:
                        session_id = sid

                # Display progress to stderr
                if etype == "system":
                    model = event.get("model", "")
                    if model:
                        print(f"  {_DIM}[{_ts()}]{_RESET} init model={_CYAN}{model}{_RESET}", file=sys.stderr)
                elif etype == "assistant":
                    msg = event.get("message", {})
                    if isinstance(msg, str):
                        try:
                            msg = json.loads(msg)
                        except (json.JSONDecodeError, ValueError):
                            msg = {}
                    for block in msg.get("content", []):
                        bt = block.get("type", "")
                        if bt == "thinking":
                            print(f"  {_DIM}[{_ts()}]{_RESET} {_YELLOW}[thinking]{_RESET} ...", file=sys.stderr)
                        elif bt == "text":
                            t = block.get("text", "")[:80]
                            print(f"  {_DIM}[{_ts()}]{_RESET} {t}", file=sys.stderr)
                        elif bt == "tool_use":
                            name = block.get("name", "?")
                            inp = block.get("input", {})
                            detail = ""
                            if name == "WebSearch":
                                detail = inp.get("query", "")
                            elif name == "WebFetch":
                                detail = inp.get("url", "")[:60]
                            print(f"  {_DIM}[{_ts()}]{_RESET} {_CYAN}[{name}]{_RESET} {detail}", file=sys.stderr)
                elif etype == "result":
                    dur = event.get("duration_ms")
                    dur_s = f"{dur / 1000:.1f}s" if dur else ""
                    print(f"  {_DIM}[{_ts()}]{_RESET} {_GREEN}[done]{_RESET} {dur_s}", file=sys.stderr)

            except (json.JSONDecodeError, ValueError):
                pass

    try:
        while True:
            try:
                ready, _, _ = select.select([master_fd], [], [], 1.0)
            except (ValueError, OSError):
                break
            if ready:
                try:
                    data = os.read(master_fd, 8192)
                except OSError:
                    break
                if not data:
                    break
                process_data(data)

            if proc.poll() is not None:
                # Drain remaining
                while True:
                    try:
                        ready, _, _ = select.select([master_fd], [], [], 0.1)
                    except (ValueError, OSError):
                        break
                    if not ready:
                        break
                    try:
                        data = os.read(master_fd, 8192)
                    except OSError:
                        break
                    if not data:
                        break
                    process_data(data)
                break
    finally:
        try:
            os.close(master_fd)
        except OSError:
            pass
        sf.close()

    proc.wait()

    # Write session ID to sidecar file
    if session_file and session_id:
        with open(session_file, "w") as f:
            f.write(session_id)

    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
