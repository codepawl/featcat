#!/usr/bin/env python3
"""Lightweight documentation consistency checks.

This intentionally avoids network access and project imports so it can run in
minimal CI/dev environments. It checks the docs that readers are expected to
trust today, while treating docs/superpowers as historical archive material.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_DOC_GLOBS = [
    "README.md",
    "CONTRIBUTING.md",
    "deploy/README.md",
    "docs/**/*.md",
    "packages/client/README.md",
    "web/tests/e2e/README.md",
]

ARCHIVE_PREFIX = Path("docs/superpowers")
ARCHIVE_NOTICE = "Archive notice:"

BANNED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bfeatcat add-source\b"), "Use `featcat source add`."),
    (re.compile(r"\bfeatcat scan\s+(?!-bulk\b)"), "Use `featcat source scan`."),
    (re.compile(r"\bfeatcat list\b"), "Use `featcat feature list`."),
    (re.compile(r"\bfeatcat docs\b"), "Use `featcat doc`."),
    (re.compile(r"\bfeatcat groups\b"), "Use `featcat group`."),
    (re.compile(r"\bfeatcat features\b"), "Use `featcat feature` or the feature API."),
    (re.compile(r"\bfeatcat sources\b"), "Use `featcat source` or the source API."),
    (re.compile(r"\bfeatcat baseline\b"), "Use `featcat monitor baseline`."),
    (re.compile(r"\bfeatcat hints\b"), "Use `featcat feature set-hint/show-hint/clear-hint`."),
    (re.compile(r"\bfeatcat health-check\b"), "Use `featcat doctor`."),
    (re.compile(r"\bfeatcat schedule\b"), "Use `featcat job schedule`."),
    (re.compile(r"\bfeatcat query\b"), "Use `featcat ask`."),
    (re.compile(r"\bFEATCAT_LLM_BASE_URL\b"), "Use `FEATCAT_LLAMACPP_URL`."),
    (re.compile(r"\bFEATCAT_LLM_ENABLED\b"), "No current setting; configure the LLM backend/URL instead."),
    (re.compile(r"\bFEATCAT_LLM_TIMEOUT_SECONDS\b"), "Use `FEATCAT_LLM_TIMEOUT`."),
    (re.compile(r"\bFEATCAT_OLLAMA_URL\b"), "Use `FEATCAT_LLAMACPP_URL`."),
    (re.compile(r"\bFEATCAT_LOG_JSON\b"), "No current setting."),
    (re.compile(r"\bFEATCAT_LOG_LEVEL\b"), "No current setting."),
]

LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")


def active_docs() -> list[Path]:
    files: set[Path] = set()
    for pattern in ACTIVE_DOC_GLOBS:
        for path in ROOT.glob(pattern):
            if path.is_file() and path.suffix == ".md":
                files.add(path.relative_to(ROOT))
    return sorted(files)


def is_archive(path: Path) -> bool:
    return path == ARCHIVE_PREFIX or ARCHIVE_PREFIX in path.parents


def split_link_target(raw: str) -> str:
    target = raw.strip()
    if not target:
        return ""
    target = target[1 : target.index(">")] if target.startswith("<") and ">" in target else target.split()[0]
    return target


def check_banned_patterns(path: Path, text: str) -> list[str]:
    if is_archive(path):
        return []
    errors: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for pattern, hint in BANNED_PATTERNS:
            if pattern.search(line):
                errors.append(f"{path}:{line_no}: stale docs pattern `{pattern.pattern}`. {hint}")
    return errors


def check_archive_notice(path: Path, text: str) -> list[str]:
    if not is_archive(path):
        return []
    if ARCHIVE_NOTICE not in "\n".join(text.splitlines()[:5]):
        return [f"{path}: missing archive notice in first five lines"]
    return []


def check_links(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    base = (ROOT / path).parent
    for match in LINK_RE.finditer(text):
        target = split_link_target(match.group(1))
        if not target or target.startswith("#"):
            continue
        parsed = urlsplit(target)
        if parsed.scheme in {"http", "https", "mailto", "app"}:
            continue
        if parsed.netloc:
            continue
        raw_path = unquote(parsed.path)
        if not raw_path:
            continue
        candidate = (base / raw_path).resolve()
        try:
            candidate.relative_to(ROOT)
        except ValueError:
            continue
        if not candidate.exists():
            line_no = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path}:{line_no}: broken local link `{target}`")
    return errors


def main() -> int:
    errors: list[str] = []
    for path in active_docs():
        text = (ROOT / path).read_text(encoding="utf-8")
        errors.extend(check_banned_patterns(path, text))
        errors.extend(check_archive_notice(path, text))
        errors.extend(check_links(path, text))

    if errors:
        print("Documentation consistency check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Documentation consistency check passed ({len(active_docs())} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
