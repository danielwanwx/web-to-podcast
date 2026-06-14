from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from .audio import convert_sample_to_wav
from .config import PipelineConfig
from .document import SourceDocument
from .extract import extract_readable_text
from .package import final_audio_path, package_article_audio
from .script import render_tts_script
from .segments import split_tts_segment_specs, write_segment_manifest
from .sources import collect_sources
from .translate import translate_document
from .tts import synthesize_article_segments
from .utils import ensure_dir, now_iso, repo_relative, write_json, write_text


PHASES = ["source", "extract", "translate", "script", "segment", "tts", "package"]
PHASE_ORDER = {phase: index for index, phase in enumerate(PHASES)}


def run_pipeline(
    config: PipelineConfig,
    *,
    force: bool = False,
    from_phase: str = "source",
    to_phase: str = "package",
) -> dict[str, Any]:
    from_phase = _normalize_phase(from_phase)
    to_phase = _normalize_phase(to_phase)
    if PHASE_ORDER[from_phase] > PHASE_ORDER[to_phase]:
        raise ValueError("from_phase must be earlier than or equal to to_phase")

    output_root = Path(config.project.output_dir).expanduser()
    ensure_dir(output_root)
    if _phase_in_window("tts", from_phase, to_phase) or _phase_in_window("package", from_phase, to_phase):
        _prepare_voice_sample(config, output_root)

    previous_manifest = _load_existing_manifest(output_root / "manifest.json")
    documents = _documents_for_run(config, output_root, from_phase, previous_manifest)

    manifest: dict[str, Any] = {
        "project": asdict(config.project),
        "started_at": now_iso(),
        "output_root": str(output_root),
        "from_phase": from_phase,
        "to_phase": to_phase,
        "resumed_from_manifest": bool(PHASE_ORDER[from_phase] > PHASE_ORDER["source"] and previous_manifest),
        "completed_to_phase": "",
        "documents": [],
        "summary": {},
    }
    write_json(output_root / "manifest.json", manifest)

    for doc in documents:
        entry = _process_document(doc, config, output_root, force=force, from_phase=from_phase, to_phase=to_phase)
        manifest["documents"].append(entry)
        manifest["summary"] = _summarize(manifest["documents"])
        manifest["completed_to_phase"] = to_phase
        manifest["updated_at"] = now_iso()
        write_json(output_root / "manifest.json", manifest)

    manifest["finished_at"] = now_iso()
    manifest["completed_to_phase"] = to_phase
    manifest["summary"] = _summarize(manifest["documents"])
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _process_document(
    doc: SourceDocument,
    config: PipelineConfig,
    output_root: Path,
    *,
    force: bool,
    from_phase: str,
    to_phase: str,
) -> dict[str, Any]:
    entry = _base_entry(doc)
    if doc.metadata.get("manifest_entry") and isinstance(doc.metadata.get("manifest_entry"), dict):
        entry.update(_preserve_manifest_paths(doc.metadata["manifest_entry"]))

    if PHASE_ORDER[from_phase] <= PHASE_ORDER["source"]:
        raw_path = _write_raw_source(doc, output_root, force=_force_phase(force, from_phase, "source"))
        entry["raw_path"] = repo_relative(raw_path, output_root)
    else:
        raw_path = _resolve_output_path(output_root, str(entry.get("raw_path") or ""))
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "source")
    if _stop_at(to_phase, "source"):
        return entry

    if PHASE_ORDER[from_phase] <= PHASE_ORDER["extract"]:
        title, clean_text = extract_readable_text(doc, extractor=config.source.extractor)
        if title and title != doc.title:
            doc.title = title
            entry["title"] = doc.title
    else:
        clean_text = _read_required_stage(output_root, entry, "clean_text_path", "extract")

    clean_path = output_root / "02_clean_text" / f"{doc.slug}.md"
    if _force_phase(force, from_phase, "extract") or not clean_path.exists():
        write_text(clean_path, clean_text.strip() + "\n")
    else:
        clean_text = clean_path.read_text(encoding="utf-8")
    entry["clean_text_path"] = repo_relative(clean_path, output_root)
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "extract")
    if _stop_at(to_phase, "extract"):
        return entry

    translated_dir = output_root / "03_translated" / doc.slug
    if PHASE_ORDER[from_phase] <= PHASE_ORDER["translate"]:
        translated_text = translate_document(doc.title, clean_text, translated_dir, config.translation, force=_force_phase(force, from_phase, "translate"))
    else:
        translated_text = _read_required_stage(output_root, entry, "translated_path", "translate")
    translated_path = translated_dir / "translated.md"
    entry["translated_path"] = repo_relative(translated_path, output_root)
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "translate")
    if _stop_at(to_phase, "translate"):
        return entry

    script_path = output_root / "04_tts_script" / f"{doc.slug}.md"
    if PHASE_ORDER[from_phase] <= PHASE_ORDER["script"]:
        script_text, script_audit = render_tts_script(translated_text, language=config.translation.target_language)
    else:
        script_text = _read_required_stage(output_root, entry, "script_path", "script")
        script_audit = {}
    if _force_phase(force, from_phase, "script") or not script_path.exists():
        write_text(script_path, script_text.strip() + "\n")
        if script_audit:
            write_json(output_root / "04_tts_script" / f"{doc.slug}.audit.json", script_audit)
    else:
        script_text = script_path.read_text(encoding="utf-8")
    entry["script_path"] = repo_relative(script_path, output_root)
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "script")
    if _stop_at(to_phase, "script"):
        return entry

    segments = split_tts_segment_specs(script_text, target_chars=config.tts.target_chars, max_chars=config.tts.max_chars)
    segment_dir = output_root / "05_segments" / doc.slug
    segment_manifest_path = segment_dir / "segments.json"
    write_segment_manifest(segment_manifest_path, segments)
    entry["segment_manifest_path"] = repo_relative(segment_manifest_path, output_root)
    entry["segment_count"] = len(segments)
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "segment")
    if _stop_at(to_phase, "segment"):
        return entry

    tts_segments = synthesize_article_segments(segments, segment_dir / "audio_chunks", config.tts, force=_force_phase(force, from_phase, "tts"))
    write_segment_manifest(segment_manifest_path, tts_segments)

    completed_wavs = [Path(item["audio_path"]) for item in tts_segments if item.get("status") == "completed" and item.get("audio_path")]
    entry["tts_completed"] = len(completed_wavs)
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "tts")
    if _stop_at(to_phase, "tts"):
        return entry

    package_info: dict[str, Any] = {"status": "skipped", "audio_path": "", "duration_seconds": 0}
    if config.tts.enabled and config.tts.provider != "none" and completed_wavs:
        package_info = package_article_audio(
            wav_paths=completed_wavs,
            segments=tts_segments,
            work_dir=segment_dir,
            output_path=final_audio_path(output_root, doc, config.output),
            config=config.output,
        )
    entry["audio"] = package_info
    entry["completed_to_phase"] = max_phase(entry.get("completed_to_phase"), "package")
    return entry


def _write_raw_source(doc: SourceDocument, output_root: Path, *, force: bool) -> Path:
    suffix = ".html" if "html" in (doc.media_type or "").lower() else ".md"
    raw_path = output_root / "01_sources" / "raw" / f"{doc.slug}{suffix}"
    if force or not raw_path.exists():
        write_text(raw_path, doc.raw_text)
    meta_path = output_root / "01_sources" / "metadata" / f"{doc.slug}.json"
    if force or not meta_path.exists():
        write_json(
            meta_path,
            {
                "id": doc.id,
                "title": doc.title,
                "section": doc.section,
                "order": doc.order,
                "source_url": doc.source_url,
                "source_path": doc.source_path,
                "media_type": doc.media_type,
                "metadata": doc.metadata,
            },
        )
    return raw_path


def _prepare_voice_sample(config: PipelineConfig, output_root: Path) -> None:
    sample = (config.tts.voice_sample or "").strip()
    if not config.tts.enabled or config.tts.provider != "vibevoice" or not sample:
        return
    source = Path(sample).expanduser()
    if not source.exists():
        raise FileNotFoundError(f"voice sample does not exist: {source}")
    target = output_root / "00_voice" / "voice_sample_24k.wav"
    if target.exists():
        config.tts.voice_sample = str(target)
        return
    convert_sample_to_wav(source, target)
    config.tts.voice_sample = str(target)


def _summarize(documents: list[dict[str, Any]]) -> dict[str, int]:
    total = len(documents)
    audio_completed = sum(1 for item in documents if item.get("audio", {}).get("status") == "completed")
    tts_completed = sum(int(item.get("tts_completed") or 0) for item in documents)
    segments = sum(int(item.get("segment_count") or 0) for item in documents)
    return {
        "documents": total,
        "audio_completed": audio_completed,
        "tts_completed_segments": tts_completed,
        "segments": segments,
    }


def _base_entry(doc: SourceDocument) -> dict[str, Any]:
    return {
        "id": doc.id,
        "title": doc.title,
        "section": doc.section,
        "order": doc.order,
        "source_url": doc.source_url,
        "source_path": doc.source_path,
        "raw_path": "",
        "clean_text_path": "",
        "translated_path": "",
        "script_path": "",
        "segment_manifest_path": "",
        "segment_count": 0,
        "tts_completed": 0,
        "completed_to_phase": "",
        "audio": {"status": "skipped", "audio_path": "", "duration_seconds": 0},
    }


def _documents_for_run(
    config: PipelineConfig,
    output_root: Path,
    from_phase: str,
    previous_manifest: dict[str, Any] | None,
) -> list[SourceDocument]:
    if PHASE_ORDER[from_phase] <= PHASE_ORDER["source"] or not previous_manifest:
        return collect_sources(config)
    docs = _documents_from_manifest(output_root, previous_manifest)
    return docs or collect_sources(config)


def _documents_from_manifest(output_root: Path, manifest: dict[str, Any]) -> list[SourceDocument]:
    raw_docs = manifest.get("documents") if isinstance(manifest, dict) else []
    if not isinstance(raw_docs, list):
        return []
    docs: list[SourceDocument] = []
    for item in raw_docs:
        if not isinstance(item, dict):
            continue
        raw_path = _resolve_output_path(output_root, str(item.get("raw_path") or ""))
        clean_path = _resolve_output_path(output_root, str(item.get("clean_text_path") or ""))
        if raw_path.exists():
            raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
            media_type = "text/html" if raw_path.suffix.lower() in {".html", ".htm"} else "text/markdown"
        elif clean_path.exists():
            raw_text = clean_path.read_text(encoding="utf-8", errors="replace")
            media_type = "text/markdown"
        else:
            continue
        docs.append(
            SourceDocument(
                id=str(item.get("id") or ""),
                title=str(item.get("title") or "Untitled"),
                raw_text=raw_text,
                source_url=str(item.get("source_url") or ""),
                source_path=str(item.get("source_path") or ""),
                section=str(item.get("section") or ""),
                order=_optional_int(item.get("order")),
                media_type=media_type,
                metadata={"manifest_entry": item},
            )
        )
    return docs


def _preserve_manifest_paths(entry: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "raw_path",
        "clean_text_path",
        "translated_path",
        "script_path",
        "segment_manifest_path",
        "segment_count",
        "tts_completed",
        "completed_to_phase",
        "audio",
    ]
    return {key: entry[key] for key in keys if key in entry}


def _read_required_stage(output_root: Path, entry: dict[str, Any], field: str, phase: str) -> str:
    value = str(entry.get(field) or "")
    path = _resolve_output_path(output_root, value)
    if not value or not path.exists():
        raise FileNotFoundError(f"cannot resume from phase {phase}: missing {field} ({value or 'empty'})")
    return path.read_text(encoding="utf-8", errors="replace")


def _load_existing_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _resolve_output_path(output_root: Path, value: str) -> Path:
    if not value:
        return output_root / "__missing__"
    path = Path(value).expanduser()
    return path if path.is_absolute() else output_root / path


def _normalize_phase(phase: str) -> str:
    normalized = (phase or "").strip().lower()
    if normalized not in PHASE_ORDER:
        raise ValueError(f"unknown phase {phase!r}; expected one of: {', '.join(PHASES)}")
    return normalized


def max_phase(left: Any, right: str) -> str:
    left_phase = str(left or "")
    if left_phase not in PHASE_ORDER:
        return right
    return left_phase if PHASE_ORDER[left_phase] >= PHASE_ORDER[right] else right


def _phase_in_window(phase: str, from_phase: str, to_phase: str) -> bool:
    return PHASE_ORDER[from_phase] <= PHASE_ORDER[phase] <= PHASE_ORDER[to_phase]


def _force_phase(force: bool, from_phase: str, phase: str) -> bool:
    return bool(force and PHASE_ORDER[phase] >= PHASE_ORDER[from_phase])


def _stop_at(to_phase: str, phase: str) -> bool:
    return PHASE_ORDER[to_phase] <= PHASE_ORDER[phase]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
