from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STAGE_PATH_FIELDS = [
    "raw_path",
    "clean_text_path",
    "translated_path",
    "script_path",
    "segment_manifest_path",
]


def inspect_run(output_dir: Path | str, *, expect_audio: bool = False) -> dict[str, Any]:
    root = Path(output_dir).expanduser()
    manifest_path = root / "manifest.json"
    report: dict[str, Any] = {
        "output_dir": str(root),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "expect_audio": bool(expect_audio),
        "ok": False,
        "issues": [],
        "summary": {
            "documents": 0,
            "stage_files_missing": 0,
            "audio_completed": 0,
            "audio_skipped": 0,
            "audio_missing": 0,
            "segment_failed": 0,
            "segment_pending": 0,
        },
        "documents": [],
    }
    if not manifest_path.exists():
        report["issues"].append({"level": "error", "message": "manifest.json is missing"})
        return report
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        report["issues"].append({"level": "error", "message": f"manifest.json is invalid: {exc}"})
        return report

    documents = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(documents, list):
        report["issues"].append({"level": "error", "message": "manifest documents must be a list"})
        return report

    report["summary"]["documents"] = len(documents)
    for doc in documents:
        doc_report = _inspect_document(root, doc if isinstance(doc, dict) else {}, expect_audio=expect_audio)
        report["documents"].append(doc_report)
        report["summary"]["stage_files_missing"] += len(doc_report["missing_stage_files"])
        report["summary"]["audio_completed"] += 1 if doc_report["audio_status"] == "completed" else 0
        report["summary"]["audio_skipped"] += 1 if doc_report["audio_status"] == "skipped" else 0
        report["summary"]["audio_missing"] += 1 if doc_report["audio_missing"] else 0
        report["summary"]["segment_failed"] += doc_report["segments"]["failed"]
        report["summary"]["segment_pending"] += doc_report["segments"]["pending"]

    for doc_report in report["documents"]:
        for missing in doc_report["missing_stage_files"]:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": f"missing stage file: {missing}"})
        if doc_report["segment_manifest_missing"]:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": "segment manifest is missing"})
        if doc_report["segments"]["failed"]:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": f"{doc_report['segments']['failed']} failed TTS segments"})
        if doc_report["segments"]["pending"] and expect_audio:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": f"{doc_report['segments']['pending']} pending TTS segments"})
        if doc_report["segments"]["missing_audio"]:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": f"{doc_report['segments']['missing_audio']} completed segment audio files are missing"})
        if doc_report["audio_missing"]:
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": "audio file is missing"})
        if expect_audio and doc_report["audio_status"] != "completed":
            report["issues"].append({"level": "error", "document": doc_report["title"], "message": f"audio status is {doc_report['audio_status']}"})

    report["ok"] = not any(issue.get("level") == "error" for issue in report["issues"])
    return report


def _inspect_document(root: Path, doc: dict[str, Any], *, expect_audio: bool) -> dict[str, Any]:
    title = str(doc.get("title") or doc.get("id") or "Untitled")
    missing_stage_files: list[str] = []
    for field in STAGE_PATH_FIELDS:
        value = str(doc.get(field) or "")
        if not value:
            missing_stage_files.append(field)
            continue
        if not _resolve_output_path(root, value).exists():
            missing_stage_files.append(value)

    segment_manifest_value = str(doc.get("segment_manifest_path") or "")
    segment_manifest_path = _resolve_output_path(root, segment_manifest_value) if segment_manifest_value else root / "__missing_segments.json"
    segment_report = _inspect_segments(segment_manifest_path)

    audio = doc.get("audio") if isinstance(doc.get("audio"), dict) else {}
    audio_status = str(audio.get("status") or "unknown")
    audio_path = str(audio.get("audio_path") or "")
    audio_missing = False
    if audio_status == "completed":
        audio_missing = not audio_path or not _resolve_output_path(root, audio_path).exists()
    elif expect_audio:
        audio_missing = True

    return {
        "id": str(doc.get("id") or ""),
        "title": title,
        "section": str(doc.get("section") or ""),
        "order": doc.get("order"),
        "missing_stage_files": missing_stage_files,
        "segment_manifest_missing": not segment_manifest_path.exists(),
        "segments": segment_report,
        "audio_status": audio_status,
        "audio_path": audio_path,
        "audio_missing": audio_missing,
    }


def _inspect_segments(segment_manifest_path: Path) -> dict[str, int]:
    summary = {"total": 0, "completed": 0, "skipped": 0, "failed": 0, "pending": 0, "missing_audio": 0}
    if not segment_manifest_path.exists():
        return summary
    try:
        segments = json.loads(segment_manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        summary["failed"] = 1
        return summary
    if not isinstance(segments, list):
        summary["failed"] = 1
        return summary
    summary["total"] = len(segments)
    for segment in segments:
        status = str(segment.get("status") if isinstance(segment, dict) else "pending")
        if status == "completed":
            summary["completed"] += 1
            audio_path = str(segment.get("audio_path") or "") if isinstance(segment, dict) else ""
            if audio_path and not Path(audio_path).expanduser().exists():
                summary["missing_audio"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "failed":
            summary["failed"] += 1
        else:
            summary["pending"] += 1
    return summary


def _resolve_output_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else root / path
