from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

from .extract import clean_source_text


def render_tts_script(text: str, language: str = "zh") -> tuple[str, dict[str, Any]]:
    """Remove symbols that tend to be read mechanically by TTS."""
    original = text or ""
    cleaned = clean_source_text(original)
    cleaned = unicodedata.normalize("NFKC", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\[\^?[^\]]+\]", "", cleaned)
    cleaned = re.sub(r"\[(?:\d+|[a-zA-Z])\]", "", cleaned)
    cleaned = re.sub(r"\s*--+\s*", "，" if language.startswith("zh") else ", ", cleaned)
    cleaned = re.sub(r"\s*[-=]{3,}\s*", "\n\n", cleaned)
    cleaned = cleaned.replace("/", " ")
    cleaned = cleaned.replace("\\", " ")
    cleaned = re.sub(r"[_#>*`|{}\[\]()<>]", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?，。！？；：])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    audit = {
        "language": language,
        "changed": cleaned != original,
        "source_chars": len(original),
        "script_chars": len(cleaned),
    }
    return cleaned, audit
