from __future__ import annotations

from dataclasses import asdict
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

    manifest: dict[str, Any] = {
        "project": asdict(config.project),
        "started_at": now_iso(),
        "output_root": str(output_root),
        "from_phase": from_phase,
        "to_phase": to_phase,
        "completed_to_phase": "",
        "documents": [],
        "summary": {},
    }
    write_json(output_root / "manifest.json", manifest)

    documents = collect_sources(config)
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

    raw_path = _write_raw_source(doc, output_root, force=_force_phase(force, from_phase, "source"))
    entry["raw_path"] = repo_relative(raw_path, output_root)
    entry["completed_to_phase"] = "source"
    if _stop_at(to_phase, "source"):
        return entry

    title, clean_text = extract_readable_text(doc)
    if title and title != doc.title:
        doc.title = title
        entry["title"] = doc.title

    clean_path = output_root / "02_clean_text" / f"{doc.slug}.md"
    if _force_phase(force, from_phase, "extract") or not clean_path.exists():
        write_text(clean_path, clean_text.strip() + "\n")
    else:
        clean_text = clean_path.read_text(encoding="utf-8")
    entry["clean_text_path"] = repo_relative(clean_path, output_root)
    entry["completed_to_phase"] = "extract"
    if _stop_at(to_phase, "extract"):
        return entry

    translated_dir = output_root / "03_translated" / doc.slug
    translated_text = translate_document(doc.title, clean_text, translated_dir, config.translation, force=_force_phase(force, from_phase, "translate"))
    translated_path = translated_dir / "translated.md"
    entry["translated_path"] = repo_relative(translated_path, output_root)
    entry["completed_to_phase"] = "translate"
    if _stop_at(to_phase, "translate"):
        return entry

    script_text, script_audit = render_tts_script(translated_text, language=config.translation.target_language)
    script_path = output_root / "04_tts_script" / f"{doc.slug}.md"
    if _force_phase(force, from_phase, "script") or not script_path.exists():
        write_text(script_path, script_text.strip() + "\n")
        write_json(output_root / "04_tts_script" / f"{doc.slug}.audit.json", script_audit)
    else:
        script_text = script_path.read_text(encoding="utf-8")
    entry["script_path"] = repo_relative(script_path, output_root)
    entry["completed_to_phase"] = "script"
    if _stop_at(to_phase, "script"):
        return entry

    segments = split_tts_segment_specs(script_text, target_chars=config.tts.target_chars, max_chars=config.tts.max_chars)
    segment_dir = output_root / "05_segments" / doc.slug
    segment_manifest_path = segment_dir / "segments.json"
    write_segment_manifest(segment_manifest_path, segments)
    entry["segment_manifest_path"] = repo_relative(segment_manifest_path, output_root)
    entry["segment_count"] = len(segments)
    entry["completed_to_phase"] = "segment"
    if _stop_at(to_phase, "segment"):
        return entry

    tts_segments = synthesize_article_segments(segments, segment_dir / "audio_chunks", config.tts, force=_force_phase(force, from_phase, "tts"))
    write_segment_manifest(segment_manifest_path, tts_segments)

    completed_wavs = [Path(item["audio_path"]) for item in tts_segments if item.get("status") == "completed" and item.get("audio_path")]
    entry["tts_completed"] = len(completed_wavs)
    entry["completed_to_phase"] = "tts"
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
    entry["completed_to_phase"] = "package"
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


def _normalize_phase(phase: str) -> str:
    normalized = (phase or "").strip().lower()
    if normalized not in PHASE_ORDER:
        raise ValueError(f"unknown phase {phase!r}; expected one of: {', '.join(PHASES)}")
    return normalized


def _phase_in_window(phase: str, from_phase: str, to_phase: str) -> bool:
    return PHASE_ORDER[from_phase] <= PHASE_ORDER[phase] <= PHASE_ORDER[to_phase]


def _force_phase(force: bool, from_phase: str, phase: str) -> bool:
    return bool(force and PHASE_ORDER[phase] >= PHASE_ORDER[from_phase])


def _stop_at(to_phase: str, phase: str) -> bool:
    return PHASE_ORDER[to_phase] <= PHASE_ORDER[phase]
