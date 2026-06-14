from __future__ import annotations

import argparse
import json
from pathlib import Path

from .vibevoice_engine import VibeVoiceEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate VibeVoice WAV segments for one article.")
    parser.add_argument("--job", required=True)
    args = parser.parse_args(argv)
    job_path = Path(args.job)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    output_dir = Path(job["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(job.get("result_path") or output_dir / "vibevoice_result.json")
    tts = job["tts"]
    engine = VibeVoiceEngine(
        model_path=tts.get("model_path", ""),
        device=tts.get("device", "mps"),
        inference_steps=int(tts.get("inference_steps", 5)),
        cfg_scale=float(tts.get("cfg_scale", 1.5)),
        max_new_tokens=int(tts.get("max_new_tokens", 220)),
        max_length_times=float(tts.get("max_length_times", 1.2)),
        voice_sample=tts.get("voice_sample", ""),
        sample_audio_leak_policy=tts.get("sample_audio_leak_policy", "trim"),
        sample_audio_leak_corr_threshold=float(tts.get("sample_audio_leak_corr_threshold", 0.88)),
        sample_audio_leak_audit_path=str(output_dir / "sample_audio_leak_audit.jsonl"),
        sample_text_leak_policy=tts.get("sample_text_leak_policy", "off"),
        sample_text_leak_phrases=tts.get("sample_text_leak_phrases", ""),
        sample_text_leak_audit_path=str(output_dir / "sample_text_leak_audit.jsonl"),
    )
    retries = int(tts.get("retries", 2))
    results = []
    failed = False
    for segment in job["segments"]:
        index = int(segment["index"])
        output_path = output_dir / f"segment_{index:04d}.wav"
        if output_path.exists() and not job.get("force", False):
            results.append({"index": index, "status": "completed", "audio_path": str(output_path), "retry_count": 0})
            continue
        last_error = ""
        for attempt in range(1, retries + 2):
            try:
                ok = engine.synthesize_to_file(
                    str(segment["text"]),
                    output_path,
                    segment_id=f"segment_{index:04d}",
                    attempt=attempt,
                )
                if ok and output_path.exists():
                    results.append({"index": index, "status": "completed", "audio_path": str(output_path), "retry_count": attempt - 1})
                    last_error = ""
                    break
                last_error = "VibeVoice returned no audio"
            except Exception as exc:
                last_error = repr(exc)
                try:
                    output_path.unlink()
                except OSError:
                    pass
        if last_error:
            failed = True
            results.append({"index": index, "status": "failed", "audio_path": str(output_path), "retry_count": retries, "error": last_error})
    result_path.write_text(json.dumps({"ok": not failed, "segments": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
