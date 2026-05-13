"""Measure prompt-token reduction from the P0.3 intent classifier.

For each prompt in `featcat-mvp-test-prompts.md` (Sections A-E, 35 prompts),
sends two `/v1/chat/completions` calls to llama.cpp at :8080:
  - one with the full 14-tool CATALOG_TOOLS inventory
  - one with the classifier-filtered subset

Captures `usage.prompt_tokens` from each response — that's the REAL count
of tokens the model evaluated, post-Jinja-template (server runs --jinja).
Also tokenizes the JSON-serialized tool schemas alone via `/tokenize` for
the schemas-only metric.

Writes `artifacts/p0-3-tokens.csv` + stdout summary.

Requires: llama.cpp server at http://localhost:8080. Fails loudly if down.
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

# Make `featcat` importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from featcat.ai.agent import SYSTEM_PROMPT  # noqa: E402
from featcat.ai.intent import classify_intent, select_tool_schemas  # noqa: E402
from featcat.ai.tools import CATALOG_TOOLS  # noqa: E402

LLAMA_URL = "http://localhost:8080"
PROMPTS_FILE = Path(__file__).resolve().parents[1] / "featcat-mvp-test-prompts.md"
OUT_DIR = Path(__file__).resolve().parents[1] / "artifacts"
OUT_CSV = OUT_DIR / "p0-3-tokens.csv"

# Prompts whose ID matches this pattern. Sections A-E only; F is manual UX.
PROMPT_ID_RE = re.compile(r"^### ([A-E]\d+)\.\s+(.+)$", re.MULTILINE)
PROMPT_BODY_RE = re.compile(r"\*\*Prompt\*\*:\s*`([^`]+)`")


def _post_json(path: str, payload: dict, timeout: int = 60) -> dict:
    """POST JSON to llama.cpp, return parsed JSON response."""
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        f"{LLAMA_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as resp:  # noqa: S310 (trusted local URL)
        return json.loads(resp.read().decode("utf-8"))


def tokenize(text: str) -> int:
    """Return token count for `text` via llama.cpp /tokenize."""
    data = _post_json("/tokenize", {"content": text})
    # Endpoint returns {"tokens": [...]} on llama.cpp server.
    return len(data["tokens"])


def prompt_tokens_for(messages: list[dict], tools: list[dict]) -> int:
    """Return real prompt_tokens count after full chat-template rendering.

    Hits /v1/chat/completions with max_tokens=1 so the model barely generates;
    the prompt_tokens field reflects the full system + messages + tools input.
    """
    payload = {
        "model": "gemma-4-E2B-it",
        "messages": messages,
        "tools": tools,
        "temperature": 0.0,
        "max_tokens": 1,
        "stream": False,
    }
    data = _post_json("/v1/chat/completions", payload, timeout=120)
    return int(data["usage"]["prompt_tokens"])


def parse_prompts(md_path: Path) -> list[tuple[str, str, str]]:
    """Yield (prompt_id, title, prompt_body) for each Section A-E prompt."""
    text = md_path.read_text(encoding="utf-8")
    out: list[tuple[str, str, str]] = []
    headers = list(PROMPT_ID_RE.finditer(text))
    for i, hdr in enumerate(headers):
        prompt_id = hdr.group(1)
        title = hdr.group(2).strip()
        section_start = hdr.end()
        section_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        section = text[section_start:section_end]
        body_match = PROMPT_BODY_RE.search(section)
        if not body_match:
            print(f"warn: no prompt body found for {prompt_id}", file=sys.stderr)
            continue
        out.append((prompt_id, title, body_match.group(1).strip()))
    return out


def measure_one(user_prompt: str) -> dict:
    """Measure schemas + total prompt tokens for one user prompt."""
    selection = classify_intent(user_prompt)
    subset_schemas, _ = select_tool_schemas(user_prompt)

    schemas_full_tokens = tokenize(json.dumps(CATALOG_TOOLS, ensure_ascii=False))
    schemas_subset_tokens = tokenize(json.dumps(subset_schemas, ensure_ascii=False))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    total_full_tokens = prompt_tokens_for(messages, CATALOG_TOOLS)
    total_subset_tokens = prompt_tokens_for(messages, subset_schemas)

    return {
        "intent_labels": ",".join(selection.labels) or "(fallback)",
        "fallback": selection.fallback,
        "tool_count_subset": len(subset_schemas),
        "tool_count_full": len(CATALOG_TOOLS),
        "schemas_full_tokens": schemas_full_tokens,
        "schemas_subset_tokens": schemas_subset_tokens,
        "schemas_savings_pct": round(100.0 * (schemas_full_tokens - schemas_subset_tokens) / schemas_full_tokens, 1),
        "total_full_tokens": total_full_tokens,
        "total_subset_tokens": total_subset_tokens,
        "total_savings_pct": round(100.0 * (total_full_tokens - total_subset_tokens) / total_full_tokens, 1),
    }


def main() -> int:
    if not PROMPTS_FILE.exists():
        print(f"error: prompts file not found at {PROMPTS_FILE}", file=sys.stderr)
        return 2

    # Sanity check: server reachable + /tokenize works.
    try:
        n = tokenize("hello world")
    except URLError as e:
        print(f"error: llama.cpp /tokenize unreachable at {LLAMA_URL}: {e}", file=sys.stderr)
        print("       start it via deploy/docker-compose.yml or dev.sh", file=sys.stderr)
        return 1
    if n < 1:
        print("error: /tokenize returned no tokens for 'hello world'", file=sys.stderr)
        return 1

    prompts = parse_prompts(PROMPTS_FILE)
    print(f"Found {len(prompts)} prompts in {PROMPTS_FILE.name}")

    OUT_DIR.mkdir(exist_ok=True)
    rows: list[dict] = []
    for pid, title, body in prompts:
        print(f"  measuring {pid}... ", end="", flush=True)
        try:
            row = measure_one(body)
        except Exception as e:  # pragma: no cover - surfaced for the operator
            print(f"FAIL ({e})")
            continue
        row.update({"prompt_id": pid, "title": title, "prompt": body})
        rows.append(row)
        print(
            f"schemas {row['schemas_full_tokens']}→{row['schemas_subset_tokens']} "
            f"({row['schemas_savings_pct']}%), "
            f"total {row['total_full_tokens']}→{row['total_subset_tokens']} "
            f"({row['total_savings_pct']}%), labels={row['intent_labels']}"
        )

    if not rows:
        print("error: no successful measurements", file=sys.stderr)
        return 1

    fieldnames = [
        "prompt_id",
        "title",
        "intent_labels",
        "fallback",
        "tool_count_full",
        "tool_count_subset",
        "schemas_full_tokens",
        "schemas_subset_tokens",
        "schemas_savings_pct",
        "total_full_tokens",
        "total_subset_tokens",
        "total_savings_pct",
        "prompt",
    ]
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    schemas_savings = [r["schemas_savings_pct"] for r in rows]
    total_savings = [r["total_savings_pct"] for r in rows]
    fallback_count = sum(1 for r in rows if r["fallback"])

    print()
    print("=== Summary ===")
    print(f"Rows: {len(rows)}")
    print(f"Fallback rate: {fallback_count}/{len(rows)} ({100.0 * fallback_count / len(rows):.1f}%)")
    print(
        f"Schemas-only savings: min={min(schemas_savings):.1f}%  "
        f"median={statistics.median(schemas_savings):.1f}%  "
        f"max={max(schemas_savings):.1f}%  "
        f"avg={statistics.mean(schemas_savings):.1f}%"
    )
    print(
        f"Total-prompt savings: min={min(total_savings):.1f}%  "
        f"median={statistics.median(total_savings):.1f}%  "
        f"max={max(total_savings):.1f}%  "
        f"avg={statistics.mean(total_savings):.1f}%"
    )
    print(f"CSV written to {OUT_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
