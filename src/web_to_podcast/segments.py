from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SENTENCE_RE = re.compile(r"[^。！？.!?；;]+[。！？.!?；;]?")
DEFAULT_PAUSES = {
    "heading": 900,
    "paragraph": 800,
    "sentence": 450,
    "soft": 180,
}


def split_tts_segment_specs(
    text: str,
    target_chars: int = 80,
    max_chars: int = 120,
    pause_ms: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if target_chars <= 0 or max_chars <= 0:
        raise ValueError("target_chars and max_chars must be positive")
    target_chars = min(target_chars, max_chars)
    pauses = {**DEFAULT_PAUSES, **(pause_ms or {})}
    specs: list[dict[str, Any]] = []
    for paragraph in _paragraphs(text):
        is_heading = _is_heading_like(paragraph)
        pieces = [paragraph] if is_heading else _sentence_pieces(paragraph)
        current = ""
        current_reason = "sentence"
        paragraph_specs: list[dict[str, str]] = []
        for piece in pieces:
            for part, reason in _soft_split_piece(piece, max_chars):
                candidate = _join_piece(current, part)
                if current and len(candidate) > target_chars:
                    paragraph_specs.append({"text": current, "pause_reason": current_reason})
                    current = part
                    current_reason = reason
                elif len(candidate) > max_chars:
                    if current:
                        paragraph_specs.append({"text": current, "pause_reason": current_reason})
                    current = part
                    current_reason = reason
                else:
                    current = candidate
                    current_reason = reason
        if current:
            paragraph_specs.append({"text": current, "pause_reason": current_reason})
        if paragraph_specs:
            paragraph_specs[-1]["pause_reason"] = "heading" if is_heading else "paragraph"
            specs.extend(paragraph_specs)

    normalized: list[dict[str, Any]] = []
    for index, spec in enumerate(specs, start=1):
        reason = spec.get("pause_reason") or "sentence"
        normalized.append(
            {
                "index": index,
                "text": spec["text"],
                "chars": len(spec["text"]),
                "pause_reason": reason,
                "pause_after_ms": int(pauses.get(reason, pauses["sentence"])),
                "status": "pending",
                "audio_path": f"segment_{index:04d}.wav",
                "retry_count": 0,
                "error": "",
            }
        )
    return normalized


def write_segment_manifest(path: Path | str, segments: list[dict[str, Any]]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def read_segment_manifest(path: Path | str) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("segment manifest must be a JSON array")
    return [dict(item) for item in data]


def _paragraphs(text: str) -> list[str]:
    source = re.sub(r"[ \t]+", " ", text or "")
    source = re.sub(r"\n{3,}", "\n\n", source).strip()
    return [part.strip() for part in re.split(r"\n\s*\n", source) if part.strip()]


def _sentence_pieces(text: str) -> list[str]:
    matches = [match.group(0).strip() for match in SENTENCE_RE.finditer(text)]
    return [match for match in matches if match] or [text]


def _soft_split_piece(piece: str, max_chars: int) -> list[tuple[str, str]]:
    if len(piece) <= max_chars:
        return [(piece, "sentence")]
    parts: list[tuple[str, str]] = []
    buffer = ""
    for token in re.split(r"([,，、:：])", piece):
        if not token:
            continue
        candidate = buffer + token
        if buffer and len(candidate) > max_chars:
            parts.extend((part, "soft") for part in _hard_split(buffer, max_chars))
            buffer = token.strip()
        else:
            buffer = candidate.strip()
    if buffer:
        parts.extend((part, "soft") for part in _hard_split(buffer, max_chars))
    return parts


def _hard_split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text.strip()]
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars) if text[index : index + max_chars].strip()]


def _join_piece(left: str, right: str) -> str:
    if not left:
        return right.strip()
    if not right:
        return left.strip()
    return f"{left.strip()} {right.strip()}".strip()


def _is_heading_like(paragraph: str) -> bool:
    return len(paragraph) <= 48 and not re.search(r"[。！？.!?；;]$", paragraph)
