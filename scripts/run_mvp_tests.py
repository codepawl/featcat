"""Run the MVP-readiness test prompts against /api/ai/chat.

Used for two purposes:
  1. Latency + accuracy benchmark of A2/A4/A6/B1/B7 (3 runs each, ON vs OFF)
  2. Full 35-prompt suite re-run for pass-rate vs PR #60 baseline

Captures per-run: wall-clock latency, tools called, intent labels (re-run
locally), full response text. Writes CSV to artifacts/.

The server must be started with the desired `FEATCAT_INTENT_FILTER`
env var; this script tags rows with `--mode` for later analysis but
does NOT toggle the server.

Usage:
  # Latency benchmark, 3 runs each, intent filter ON
  python scripts/run_mvp_tests.py --prompts A2,A4,A6,B1,B7 --runs 3 --mode on

  # Same after restarting server with FEATCAT_INTENT_FILTER=off
  python scripts/run_mvp_tests.py --prompts A2,A4,A6,B1,B7 --runs 3 --mode off

  # Full 35-prompt suite (one run each)
  python scripts/run_mvp_tests.py --runs 1 --mode on
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# Make `featcat` importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from featcat.ai.intent import classify_intent  # noqa: E402

CHAT_URL = "http://localhost:8000/api/ai/chat"
PROMPTS_FILE = Path(__file__).resolve().parents[1] / "featcat-mvp-test-prompts.md"
OUT_DIR = Path(__file__).resolve().parents[1] / "artifacts"

PROMPT_ID_RE = re.compile(r"^### ([A-E]\d+)\.\s+(.+)$", re.MULTILINE)
PROMPT_BODY_RE = re.compile(r"\*\*Prompt\*\*:\s*`([^`]+)`")

# Pass criteria for accuracy prompts (must call at least one of the listed tools).
# Source: featcat-mvp-test-prompts.md "Expected" / "Pass criteria" sections.
ACCURACY_CRITERIA: dict[str, set[str]] = {
    "A2": {"count_features", "catalog_summary"},
    "A4": {"list_features", "count_features"},
    "A6": {"get_group"},
}


def parse_prompts(md_path: Path) -> dict[str, tuple[str, str]]:
    """Return {prompt_id: (title, body)} for each Section A-E prompt."""
    text = md_path.read_text(encoding="utf-8")
    out: dict[str, tuple[str, str]] = {}
    headers = list(PROMPT_ID_RE.finditer(text))
    for i, hdr in enumerate(headers):
        prompt_id = hdr.group(1)
        title = hdr.group(2).strip()
        section_start = hdr.end()
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section = text[section_start:section_end]
        body_match = PROMPT_BODY_RE.search(section)
        if body_match:
            out[prompt_id] = (title, body_match.group(1).strip())
    return out


def post_chat(query: str, timeout: int = 300) -> tuple[float, list[str], str, bool]:
    """POST query to /api/ai/chat, consume SSE stream.

    Returns (latency_s, tools_called, full_response_text, completed).
    `completed` is True iff a `done` event was received before timeout.
    """
    body = json.dumps({"query": query}).encode("utf-8")
    req = Request(
        CHAT_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    tools_called: list[str] = []
    response_text = ""
    completed = False
    started = time.monotonic()

    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted local URL)
        # SSE format: "event: message\ndata: {...}\n\n"
        for raw_line in resp:
            line = raw_line.decode("utf-8").rstrip("\r\n")
            if not line.startswith("data: "):
                continue
            payload_str = line[6:]
            try:
                payload = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            etype = payload.get("type", "")
            if etype == "tool_call":
                name = payload.get("name", "")
                if name:
                    tools_called.append(name)
            elif etype == "token":
                response_text += payload.get("content", "")
            elif etype == "done":
                completed = True
                break

    elapsed = time.monotonic() - started
    return elapsed, tools_called, response_text, completed


def select_prompts(all_prompts: dict[str, tuple[str, str]], wanted: list[str] | None) -> list[tuple[str, str, str]]:
    """Return ordered list of (id, title, body). `wanted=None` means all."""
    if wanted is None:
        keys = sorted(all_prompts.keys(), key=_prompt_sort_key)
    else:
        keys = [k.strip() for k in wanted if k.strip() in all_prompts]
        missing = [k.strip() for k in wanted if k.strip() not in all_prompts]
        if missing:
            print(f"warn: prompts not found: {missing}", file=sys.stderr)
    return [(k, *all_prompts[k]) for k in keys]


def _prompt_sort_key(pid: str) -> tuple[str, int]:
    # "A10" should sort after "A2".
    return (pid[0], int(pid[1:]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompts",
        type=str,
        default=None,
        help="Comma-separated prompt IDs (e.g. A2,A4,B1). Default: all Section A-E.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Runs per prompt (default 1, use 3 for latency benchmark).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=("on", "off", "unknown"),
        default="unknown",
        help="Tag for FEATCAT_INTENT_FILTER mode the server is running with.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output CSV path. Default: artifacts/p0-3-mvp-{mode}.csv",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Per-prompt HTTP read timeout, seconds (default 300).",
    )
    args = parser.parse_args()

    all_prompts = parse_prompts(PROMPTS_FILE)
    wanted = args.prompts.split(",") if args.prompts else None
    targets = select_prompts(all_prompts, wanted)
    if not targets:
        print("error: no prompts selected", file=sys.stderr)
        return 2

    OUT_DIR.mkdir(exist_ok=True)
    out_path = Path(args.out) if args.out else (OUT_DIR / f"p0-3-mvp-{args.mode}.csv")

    print(f"Server: {CHAT_URL}")
    print(f"Mode tag: {args.mode}")
    print(f"Prompts: {len(targets)} × {args.runs} run(s) = {len(targets) * args.runs} requests")
    print(f"Output:  {out_path}")
    print()

    fieldnames = [
        "prompt_id",
        "run",
        "mode",
        "title",
        "intent_labels",
        "selected_tools",
        "fallback",
        "latency_s",
        "completed",
        "tools_actually_called",
        "match",
        "accuracy_pass",
        "prompt",
        "response_chars",
        "response_excerpt",
    ]

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for pid, title, body in targets:
            selection = classify_intent(body)
            selected = list(selection.tools)
            crit = ACCURACY_CRITERIA.get(pid)
            for run_idx in range(1, args.runs + 1):
                print(f"  {pid} run {run_idx}/{args.runs}... ", end="", flush=True)
                try:
                    latency, called, text, completed = post_chat(body, timeout=args.timeout)
                except URLError as e:
                    print(f"FAIL ({e})")
                    print(
                        f"error: cannot reach {CHAT_URL}. Is featcat serve running?",
                        file=sys.stderr,
                    )
                    return 1
                except TimeoutError:
                    print(f"TIMEOUT after {args.timeout}s")
                    latency, called, text, completed = float(args.timeout), [], "", False
                except Exception as e:  # pragma: no cover
                    print(f"ERROR ({e})")
                    continue

                match = all(c in selected for c in called) if called else True
                if crit is None:
                    accuracy_pass = "n/a"
                elif any(c in crit for c in called):
                    accuracy_pass = "pass"
                else:
                    accuracy_pass = "fail"

                writer.writerow(
                    {
                        "prompt_id": pid,
                        "run": run_idx,
                        "mode": args.mode,
                        "title": title,
                        "intent_labels": ",".join(selection.labels) or "(fallback)",
                        "selected_tools": ",".join(selected),
                        "fallback": selection.fallback,
                        "latency_s": round(latency, 2),
                        "completed": completed,
                        "tools_actually_called": ",".join(called),
                        "match": match,
                        "accuracy_pass": accuracy_pass,
                        "prompt": body,
                        "response_chars": len(text),
                        "response_excerpt": text[:160].replace("\n", " "),
                    }
                )
                print(f"{latency:.1f}s called=[{','.join(called) or '-'}] acc={accuracy_pass} completed={completed}")
            f.flush()

    print()
    print(f"CSV written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
