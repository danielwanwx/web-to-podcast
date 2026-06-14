from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .config import TTSConfig
from .utils import write_json
from .vibevoice_engine import VibeVoiceEngine


def synthesize_article_segments(
    segments: list[dict[str, Any]],
    output_dir: Path,
    config: TTSConfig,
    *,
    force: bool = False,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not config.enabled or config.provider == "none":
        return [_with_audio_status(segment, "skipped", "") for segment in segments]
    if config.provider != "vibevoice":
        raise ValueError(f"unsupported TTS provider: {config.provider}")
    if config.isolate_process:
        return _synthesize_in_worker(segments, output_dir, config, force=force)
    return _synthesize_direct(segments, output_dir, config, force=force)


def _synthesize_in_worker(segments: list[dict[str, Any]], output_dir: Path, config: TTSConfig, *, force: bool) -> list[dict[str, Any]]:
    job_path = output_dir / "vibevoice_job.json"
    result_path = output_dir / "vibevoice_result.json"
    write_json(
        job_path,
        {
            "output_dir": str(output_dir),
            "result_path": str(result_path),
            "force": force,
            "tts": asdict(config),
            "segments": segments,
        },
    )
    env = dict(os.environ)
    repo_src = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = repo_src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, "-m", "web_to_podcast.vibevoice_worker", "--job", str(job_path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=config.timeout_seconds,
        env=env,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "VibeVoice worker failed"
        raise RuntimeError(detail)
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    if not payload.get("ok"):
        raise RuntimeError(f"VibeVoice worker reported failed segments: {payload}")
    return _merge_worker_results(segments, payload.get("segments") or [])


def _synthesize_direct(segments: list[dict[str, Any]], output_dir: Path, config: TTSConfig, *, force: bool) -> list[dict[str, Any]]:
    engine = VibeVoiceEngine(
        model_path=config.model_path,
        device=config.device,
        inference_steps=config.inference_steps,
        cfg_scale=config.cfg_scale,
        max_new_tokens=config.max_new_tokens,
        max_length_times=config.max_length_times,
        voice_sample=config.voice_sample,
        sample_audio_leak_policy=config.sample_audio_leak_policy,
        sample_audio_leak_corr_threshold=config.sample_audio_leak_corr_threshold,
        sample_audio_leak_audit_path=str(output_dir / "sample_audio_leak_audit.jsonl"),
        sample_text_leak_policy=config.sample_text_leak_policy,
        sample_text_leak_phrases=config.sample_text_leak_phrases,
        sample_text_leak_audit_path=str(output_dir / "sample_text_leak_audit.jsonl"),
    )
    results: list[dict[str, Any]] = []
    for segment in segments:
        index = int(segment["index"])
        path = output_dir / f"segment_{index:04d}.wav"
        if path.exists() and not force:
            results.append(_with_audio_status(segment, "completed", str(path)))
            continue
        last_error = ""
        for attempt in range(1, config.retries + 2):
            try:
                if engine.synthesize_to_file(str(segment["text"]), path, segment_id=f"segment_{index:04d}", attempt=attempt):
                    updated = _with_audio_status(segment, "completed", str(path))
                    updated["retry_count"] = attempt - 1
                    results.append(updated)
                    last_error = ""
                    break
                last_error = "VibeVoice returned no audio"
            except Exception as exc:
                last_error = repr(exc)
                try:
                    path.unlink()
                except OSError:
                    pass
        if last_error:
            updated = _with_audio_status(segment, "failed", str(path))
            updated["error"] = last_error
            updated["retry_count"] = config.retries
            results.append(updated)
            raise RuntimeError(f"segment {index} failed: {last_error}")
    return results


def _merge_worker_results(segments: list[dict[str, Any]], results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_index = {int(item["index"]): item for item in results}
    merged: list[dict[str, Any]] = []
    for segment in segments:
        index = int(segment["index"])
        result = by_index.get(index, {})
        updated = dict(segment)
        updated["status"] = str(result.get("status") or "pending")
        updated["audio_path"] = str(result.get("audio_path") or "")
        updated["retry_count"] = int(result.get("retry_count") or 0)
        updated["error"] = str(result.get("error") or "")
        merged.append(updated)
    return merged


def _with_audio_status(segment: dict[str, Any], status: str, audio_path: str) -> dict[str, Any]:
    updated = dict(segment)
    updated["status"] = status
    updated["audio_path"] = audio_path
    return updated
