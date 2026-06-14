from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any


def require_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for audio packaging")
    return ffmpeg


def require_ffprobe() -> str:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for audio inspection")
    return ffprobe


def convert_sample_to_wav(input_path: Path | str, output_path: Path | str) -> Path:
    ffmpeg = require_ffmpeg()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-sample_fmt",
            "s16",
            str(output),
        ]
    )
    return output


def write_silence_wav(path: Path | str, duration_ms: int, sample_rate: int = 24000) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = max(1, int(sample_rate * max(0, duration_ms) / 1000))
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(b"\x00\x00" * frames)
    return output


def concat_wavs(wav_paths: list[Path | str], output_wav: Path | str) -> Path:
    if not wav_paths:
        raise ValueError("at least one WAV path is required")
    ffmpeg = require_ffmpeg()
    output = Path(output_wav)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp_dir:
        list_path = Path(tmp_dir) / "wav-list.txt"
        lines = [f"file {shlex.quote(str(Path(path).resolve()))}" for path in wav_paths]
        list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _run(
            [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_path),
                "-ac",
                "1",
                "-ar",
                "24000",
                "-sample_fmt",
                "s16",
                str(output),
            ]
        )
    return output


def concat_wavs_with_pauses(
    wav_paths: list[Path | str],
    output_wav: Path | str,
    *,
    segment_entries: list[dict[str, Any]] | None = None,
    silence_dir: Path | str | None = None,
    pause_plan_path: Path | str | None = None,
    sample_rate: int = 24000,
) -> Path:
    if segment_entries is not None and len(segment_entries) != len(wav_paths):
        raise ValueError("segment_entries must match wav_paths length")
    output = Path(output_wav)
    work_dir = Path(silence_dir) if silence_dir else output.parent / "silence_chunks"
    work_dir.mkdir(parents=True, exist_ok=True)
    items: list[Path] = []
    plan: list[dict[str, Any]] = []
    for index, wav_path in enumerate(wav_paths, start=1):
        path = Path(wav_path)
        items.append(path)
        plan.append({"type": "audio", "index": index, "path": str(path)})
        if index == len(wav_paths):
            continue
        entry = segment_entries[index - 1] if segment_entries else {}
        pause_ms = _int_or(entry.get("pause_after_ms") if isinstance(entry, dict) else None, 450)
        reason = str(entry.get("pause_reason") or "sentence") if isinstance(entry, dict) else "sentence"
        if pause_ms > 0:
            silence = work_dir / f"pause_{index:04d}_{pause_ms}ms.wav"
            write_silence_wav(silence, pause_ms, sample_rate=sample_rate)
            items.append(silence)
            plan.append({"type": "silence", "after_index": index, "duration_ms": pause_ms, "reason": reason, "path": str(silence)})
    if pause_plan_path:
        pause_path = Path(pause_plan_path)
        pause_path.parent.mkdir(parents=True, exist_ok=True)
        pause_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return concat_wavs(items, output)


def encode_m4a(input_wav: Path | str, output_m4a: Path | str, bitrate: str = "128k") -> Path:
    ffmpeg = require_ffmpeg()
    output = Path(output_m4a)
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([ffmpeg, "-y", "-i", str(input_wav), "-vn", "-c:a", "aac", "-b:a", bitrate, str(output)])
    return output


def probe_audio(path: Path | str) -> dict[str, Any]:
    ffprobe = require_ffprobe()
    result = subprocess.run(
        [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "ffprobe failed")
    payload = json.loads(result.stdout or "{}")
    stream = next((item for item in payload.get("streams", []) if item.get("codec_type") == "audio"), {})
    duration_raw = stream.get("duration") or payload.get("format", {}).get("duration") or 0
    try:
        duration = round(float(duration_raw), 3)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration_seconds": duration,
        "sample_rate": _int_or(stream.get("sample_rate"), 0),
        "channels": _int_or(stream.get("channels"), 0),
        "codec": stream.get("codec_name", ""),
    }


def _run(args: list[str]) -> None:
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"command failed: {args[0]}")


def _int_or(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
