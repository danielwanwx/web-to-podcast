from __future__ import annotations

from pathlib import Path
from typing import Any

from .audio import concat_wavs_with_pauses, encode_m4a, probe_audio
from .config import OutputConfig
from .document import SourceDocument
from .utils import ensure_dir, numbered_title, safe_filename


def final_audio_path(root: Path, document: SourceDocument, config: OutputConfig) -> Path:
    base = root / "06_podcast"
    if document.section:
        for part in document.section.split("/"):
            if part.strip():
                base = base / safe_filename(part.strip())
    ensure_dir(base)
    suffix = ".m4a" if config.audio_format.lower() == "m4a" else ".wav"
    if config.naming == "official-title":
        name = numbered_title(document.order, document.title)
    else:
        name = document.slug
    return base / f"{safe_filename(name)}{suffix}"


def package_article_audio(
    *,
    wav_paths: list[Path],
    segments: list[dict[str, Any]],
    work_dir: Path,
    output_path: Path,
    config: OutputConfig,
) -> dict[str, Any]:
    if not wav_paths:
        return {"status": "skipped", "audio_path": "", "duration_seconds": 0}
    work_dir.mkdir(parents=True, exist_ok=True)
    concat_wav = work_dir / "article_with_pauses.wav"
    concat_wavs_with_pauses(
        wav_paths,
        concat_wav,
        segment_entries=segments,
        silence_dir=work_dir / "silence_chunks",
        pause_plan_path=work_dir / "pause_plan.json",
    )
    if config.audio_format.lower() == "m4a":
        encode_m4a(concat_wav, output_path, bitrate=config.bitrate)
        if not config.keep_wav:
            try:
                concat_wav.unlink()
            except OSError:
                pass
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        concat_wav.replace(output_path)
    try:
        info = probe_audio(output_path)
    except Exception:
        info = {"duration_seconds": 0}
    return {"status": "completed", "audio_path": str(output_path), **info}
