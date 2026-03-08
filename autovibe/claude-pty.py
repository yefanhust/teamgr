#!/usr/bin/env python3
"""Run Claude CLI with a real pty for real-time streaming output.

Usage: claude-pty.py [--output-file FILE] [--] CLAUDE_ARGS...

Claude CLI buffers stdout when it detects a non-tty (pipe). This wrapper
creates a pseudo-terminal so Claude flushes output immediately.

When --output-format stream-json is in the args, it parses JSON events and
displays human-readable progress. Otherwise it passes raw output through.

Claude Code stream-json format (NOT Anthropic API SSE format):
- system:    {"type":"system", "subtype":"init", "model":"...", ...}
- assistant: {"type":"assistant", "message":{"content":[...blocks...]}}
  Content blocks: {"type":"text","text":"..."} or {"type":"tool_use","name":"...","input":{...}}
- user:      {"type":"user", ...} (tool results)
- result:    {"type":"result", "result":"final text", "cost_usd":..., "duration_ms":...}
"""
import json
import os
import pty
import re
import select
import subprocess
import sys
import termios
import time
from datetime import datetime


def _ts():
    """Current timestamp string."""
    return datetime.now().strftime("%H:%M:%S")


# ANSI color helpers
_RESET = "\033[0m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_MAGENTA = "\033[35m"
_RED = "\033[31m"

# Tool name → color
_TOOL_COLORS = {
    "Read": _CYAN, "Edit": _YELLOW, "Write": _YELLOW,
    "Bash": _MAGENTA, "Grep": _BLUE, "Glob": _BLUE,
    "Agent": _GREEN, "ToolSearch": _DIM,
    "TodoWrite": _DIM, "NotebookEdit": _YELLOW,
}


class StreamParser:
    """Parser for Claude Code CLI stream-json events."""

    def __init__(self):
        self.last_event_time = time.monotonic()
        self.last_line = None  # buffered line, printed when next event arrives (with elapsed)
        self.session_id = None  # extracted from first event's sessionId field

    def _flush_last(self):
        """Flush the buffered line with elapsed time appended."""
        if self.last_line is None:
            return ""
        now = time.monotonic()
        elapsed = now - self.last_event_time
        self.last_event_time = now
        line = self.last_line
        if elapsed >= 0.1:
            dur = f"{elapsed:.1f}s" if elapsed < 60 else f"{elapsed / 60:.1f}m"
            line = line.rstrip("\n") + f"  {_DIM}({dur}){_RESET}\n"
        self.last_line = None
        return line

    @staticmethod
    def _tool_summary(name, inp):
        """Extract key info from tool input dict."""
        if not isinstance(inp, dict):
            return ""
        if name in ("Read",):
            fp = inp.get("file_path", "")
            extra = ""
            if inp.get("offset") or inp.get("limit"):
                extra = f" L{inp.get('offset', 1)}-{(inp.get('offset') or 1) + (inp.get('limit') or 0)}"
            return fp + extra
        elif name in ("Edit",):
            return inp.get("file_path", "")
        elif name in ("Write",):
            return inp.get("file_path", "")
        elif name in ("Bash",):
            cmd = inp.get("command", "")
            return cmd.split("\n")[0][:120] if cmd else ""
        elif name in ("Grep",):
            parts = []
            if inp.get("pattern"):
                parts.append(f'/{inp["pattern"]}/')
            if inp.get("path"):
                parts.append(inp["path"])
            return " ".join(parts)
        elif name in ("Glob",):
            return inp.get("pattern", "")
        elif name in ("ToolSearch",):
            return inp.get("query", "")
        else:
            for v in inp.values():
                if isinstance(v, str) and v:
                    return v[:80]
            return ""

    def parse(self, line):
        """Parse one stream-json line. Returns text to display or None."""
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            return None

        # Capture session ID from events
        if self.session_id is None:
            # stream-json may use sessionId or session_id
            sid = event.get("sessionId") or event.get("session_id") or event.get("conversationId")
            if sid:
                self.session_id = sid

        etype = event.get("type", "")

        if etype == "system":
            flushed = self._flush_last()
            subtype = event.get("subtype", "")
            model = event.get("model", "")
            if subtype == "init" and model:
                self.last_line = f"  {_DIM}[{_ts()}]{_RESET} {_BOLD}init{_RESET}  model={_CYAN}{model}{_RESET}\n"
            else:
                msg = event.get("message", "") or subtype
                self.last_line = f"  {_DIM}[{_ts()}]{_RESET} {msg}\n" if msg else None
            return flushed or None

        elif etype == "assistant":
            flushed = self._flush_last()
            msg = event.get("message", {})
            if isinstance(msg, str):
                try:
                    msg = json.loads(msg)
                except (json.JSONDecodeError, ValueError):
                    self.last_line = f"  {_DIM}[{_ts()}]{_RESET} {msg[:150]}\n"
                    return flushed or None

            content = msg.get("content", [])
            if not content:
                return flushed or None

            new_lines = []
            for block in content:
                bt = block.get("type", "")
                if bt == "text":
                    text = block.get("text", "").strip()
                    if text:
                        text_lines = text.split("\n")
                        new_lines.append(f"  {_DIM}[{_ts()}]{_RESET} {text_lines[0]}")
                        for tline in text_lines[1:]:
                            new_lines.append(f"    {tline}")
                elif bt == "tool_use":
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    summary = self._tool_summary(name, inp)
                    tc = _TOOL_COLORS.get(name, _CYAN)
                    s = f"  {_DIM}[{_ts()}]{_RESET} {tc}[tool] {name}{_RESET}"
                    if summary:
                        s += f"  {_DIM}{summary}{_RESET}"
                    new_lines.append(s)

            if not new_lines:
                return flushed or None

            # All lines except the last get output immediately;
            # the last line is buffered to attach elapsed time later
            immediate = new_lines[:-1]
            self.last_line = new_lines[-1] + "\n"
            result = flushed + "\n".join(immediate) + ("\n" if immediate else "")
            return result if result.strip() else None

        elif etype == "result":
            flushed = self._flush_last()
            cost = event.get("cost_usd")
            duration = event.get("duration_ms")
            stats = []
            if cost is not None:
                stats.append(f"${cost:.4f}")
            if duration is not None:
                stats.append(f"{duration / 1000:.1f}s")
            return flushed + f"\n  {_DIM}[{_ts()}]{_RESET} {_GREEN}{_BOLD}[done]{_RESET} {_GREEN}{' '.join(stats)}{_RESET}\n"

        # Skip user events (tool results) and unknown types
        return None

    def flush_final(self):
        """Flush any remaining buffered line at end of stream."""
        return self._flush_last()


def _find_session_from_fs(start_time):
    """Find session ID from Claude's project .jsonl files.

    Looks for .jsonl files created after start_time in the teamgr project dir.
    Returns the basename (without .jsonl) of the newest matching file.
    """
    import glob as _glob
    project_dirs = _glob.glob(os.path.expanduser("~/.claude/projects/*teamgr*/"))
    for pd in project_dirs:
        jsonls = [f for f in _glob.glob(os.path.join(pd, "*.jsonl"))
                  if os.path.getmtime(f) >= start_time]
        if jsonls:
            # Pick the one created closest to start_time (newest creation)
            # Use ctime as proxy for creation time
            newest = max(jsonls, key=os.path.getctime)
            return os.path.basename(newest).replace(".jsonl", "")
    return None


def main():
    args = sys.argv[1:]
    output_file = None

    if "--output-file" in args:
        idx = args.index("--output-file")
        output_file = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if "--" in args:
        args.remove("--")

    if not args:
        print("Usage: claude-pty.py [--output-file FILE] [--] CLAUDE_ARGS...",
              file=sys.stderr)
        sys.exit(1)

    is_stream_json = "--output-format" in args and "stream-json" in args

    # Create pty pair
    master_fd, slave_fd = pty.openpty()

    # Disable output post-processing to avoid CR/LF translation
    attrs = termios.tcgetattr(slave_fd)
    attrs[1] = attrs[1] & ~termios.OPOST
    termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)

    proc_start_time = time.time()

    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    raw_chunks = []
    line_buffer = b""
    parser = StreamParser()

    def process_data(data):
        nonlocal line_buffer
        raw_chunks.append(data)

        if is_stream_json:
            line_buffer += data
            while b"\n" in line_buffer:
                line, line_buffer = line_buffer.split(b"\n", 1)
                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue
                display = parser.parse(text)
                if display:
                    sys.stdout.write(display)
                    sys.stdout.flush()
        else:
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()

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
                # Drain remaining output
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

    proc.wait()

    # Flush any remaining buffered line
    if is_stream_json:
        remaining = parser.flush_final()
        if remaining:
            sys.stdout.write(remaining)
            sys.stdout.flush()

    # Save final result to file
    if output_file:
        full = b"".join(raw_chunks)
        if is_stream_json:
            result_text = ""
            for raw_line in full.split(b"\n"):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    evt = json.loads(raw_line)
                    if evt.get("type") == "result":
                        result_text = evt.get("result", "")
                except (json.JSONDecodeError, ValueError):
                    pass
            with open(output_file, "w") as f:
                f.write(result_text)
            # Write session ID to sidecar file for caller to pick up
            # Try from parsed events first, fall back to filesystem
            sid = parser.session_id
            if not sid:
                sid = _find_session_from_fs(proc_start_time)
            if sid:
                with open(output_file + ".session", "w") as f:
                    f.write(sid)
        else:
            clean = re.sub(rb"\x1b\[[0-9;]*[a-zA-Z]", b"", full)
            clean = re.sub(rb"\x1b\][^\x07]*\x07", b"", clean)
            clean = re.sub(rb"\r\n", b"\n", clean)
            clean = re.sub(rb"\r", b"\n", clean)
            with open(output_file, "wb") as f:
                f.write(clean)

    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
