"""Language detection utilities."""

from __future__ import annotations

import re

_VIETNAMESE_RE = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
    r"ùúụủũưừứựửữỳýỵỷỹđ]",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Detect language from text. Returns 'vi' for Vietnamese, 'en' otherwise."""
    return "vi" if _VIETNAMESE_RE.search(text) else "en"


def is_vietnamese(text: str) -> bool:
    """Check if text contains Vietnamese diacritics."""
    return detect_language(text) == "vi"


LANGUAGE_INSTRUCTION_VI = "Respond in Vietnamese. Feature names, JSON keys, and code stay in English."


def localize_system_prompt(base_prompt: str, lang: str) -> str:
    """Append Vietnamese response instruction if needed."""
    if lang == "vi":
        return f"{base_prompt}\n\n{LANGUAGE_INSTRUCTION_VI}"
    return base_prompt
