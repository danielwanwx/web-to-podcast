from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dir(path: Path | str) -> Path:
    out = Path(path)
    out.mkdir(parents=True, exist_ok=True)
    return out


def read_text(path: Path | str) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def write_text(path: Path | str, text: str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def write_json(path: Path | str, data: Any) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def stable_id(*parts: str) -> str:
    raw = "\n".join(part for part in parts if part)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def slugify(value: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = re.sub(r"[^\w\s.-]+", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip(".-")
    return text or fallback


def safe_filename(value: str, fallback: str = "item") -> str:
    text = unicodedata.normalize("NFKC", value or "").strip()
    text = re.sub(r"[/\\:*?\"<>|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def numbered_title(order: int | None, title: str) -> str:
    clean = safe_filename(title, "Untitled")
    if order is None:
        return clean
    return f"{int(order)}. {clean}"


def coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def repo_relative(path: Path | str, base: Path | str) -> str:
    try:
        return str(Path(path).resolve().relative_to(Path(base).resolve()))
    except ValueError:
        return str(path)
