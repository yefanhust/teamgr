#!/usr/bin/env python3
"""Parse Claude CLI stream-json output and display human-readable progress.

Usage: claude ... --output-format stream-json | claude-stream-parser.py [output_file]

Reads stream-json from stdin line by line, prints progress to stdout in
real-time, and saves the final result text to output_file (if provided).
"""
import json
import sys


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else None
    result_text = ""
    in_text_block = False

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        etype = event.get("type", "")

        if etype == "system":
            msg = event.get("message", "") or event.get("subtype", "")
            if msg:
                print(f"  [system] {msg}", flush=True)

        elif etype == "assistant":
            # New assistant turn
            print("  [assistant] thinking...", flush=True)

        elif etype == "content_block_start":
            block = event.get("content_block", {})
            btype = block.get("type", "")
            if btype == "tool_use":
                name = block.get("name", "?")
                print(f"  [tool_use] {name}", flush=True)
            elif btype == "text":
                in_text_block = True

        elif etype == "content_block_delta":
            delta = event.get("delta", {})
            dtype = delta.get("type", "")
            if dtype == "text_delta":
                text = delta.get("text", "")
                if text:
                    sys.stdout.write(text)
                    sys.stdout.flush()
            elif dtype == "input_json_delta":
                # Tool input streaming - show partial JSON
                partial = delta.get("partial_json", "")
                if partial:
                    sys.stdout.write(partial)
                    sys.stdout.flush()

        elif etype == "content_block_stop":
            if in_text_block:
                print("", flush=True)  # newline after text block
                in_text_block = False
            else:
                print("", flush=True)  # newline after tool input

        elif etype == "result":
            result_text = event.get("result", "")
            cost = event.get("cost_usd")
            duration = event.get("duration_ms")
            api_dur = event.get("duration_api_ms")
            stats = []
            if cost is not None:
                stats.append(f"${cost:.4f}")
            if duration is not None:
                stats.append(f"{duration / 1000:.1f}s")
            if api_dur is not None:
                stats.append(f"api:{api_dur / 1000:.1f}s")
            stat_str = " ".join(stats)
            print(f"\n  [done] {stat_str}", flush=True)

    # Save final result
    if output_file and result_text:
        with open(output_file, "w") as f:
            f.write(result_text)


if __name__ == "__main__":
    main()
