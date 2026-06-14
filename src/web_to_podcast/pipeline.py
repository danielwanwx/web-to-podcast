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


def run_pipeline(config: PipelineConfig, *, force: bool = False) -> dict[str, Any]:
    output_root = Path(config.project.output_dir).expanduser()
    ensure_dir(output_root)
    _prepare_voice_sample(config, output_root)

    manifest: dict[str, Any] = {
        "project": asdict(config.project),
        "started_at": now_iso(),
        "output_root": str(output_root),
        "documents": [],
        "summary": {},
    }
    write_json(output_root / "manifest.json", manifest)

    documents = collect_sources(config)
    for doc in documents:
        entry = _process_document(doc, config, output_root, force=force)
        manifest["documents"].append(entry)
        manifest["summary"] = _summarize(manifest["documents"])
        manifest["updated_at"] = now_iso()
        write_json(output_root / "manifest.json", manifest)

    manifest["finished_at"] = now_iso()
    manifest["summary"] = _summarize(manifest["documents"])
    write_json(output_root / "manifest.json", manifest)
    return manifest


def _process_document(doc: SourceDocument, config: PipelineConfig, output_root: Path, *, force: bool) -> dict[str, Any]:
    raw_path = _write_raw_source(doc, output_root, force=force)
    title, clean_text = extract_readable_text(doc)
    if title and title != doc.title:
        doc.title = title

    clean_path = output_root / "02_clean_text" / f"{doc.slug}.md"
    if force or not clean_path.exists():
        write_text(clean_path, clean_text.strip() + "\n")
    else:
        clean_text = clean_path.read_text(encoding="utf-8")

    translated_dir = output_root / "03_translated" / doc.slug
    translated_text = translate_document(doc.title, clean_text, translated_dir, config.translation, force=force)
    translated_path = translated_dir / "translated.md"

    script_text, script_audit = render_tts_script(translated_text, language=config.translation.target_language)
    script_path = output_root / "04_tts_script" / f"{doc.slug}.md"
    if force or not script_path.exists():
        write_text(script_path, script_text.strip() + "\n")
        write_json(output_root / "04_tts_script" / f"{doc.slug}.audit.json", script_audit)
    else:
        script_text = script_path.read_text(encoding="utf-8")

    segments = split_tts_segment_specs(script_text, target_chars=config.tts.target_chars, max_chars=config.tts.max_chars)
    segment_dir = output_root / "05_segments" / doc.slug
    segment_manifest_path = segment_dir / "segments.json"
    write_segment_manifest(segment_manifest_path, segments)

    tts_segments = synthesize_article_segments(segments, segment_dir / "audio_chunks", config.tts, force=force)
    write_segment_manifest(segment_manifest_path, tts_segments)

    completed_wavs = [Path(item["audio_path"]) for item in tts_segments if item.get("status") == "completed" and item.get("audio_path")]
    package_info: dict[str, Any] = {"status": "skipped", "audio_path": "", "duration_seconds": 0}
    if config.tts.enabled and config.tts.provider != "none" and completed_wavs:
        package_info = package_article_audio(
            wav_paths=completed_wavs,
            segments=tts_segments,
            work_dir=segment_dir,
            output_path=final_audio_path(output_root, doc, config.output),
            config=config.output,
        )

    return {
        "id": doc.id,
        "title": doc.title,
        "section": doc.section,
        "order": doc.order,
        "source_url": doc.source_url,
        "source_path": doc.source_path,
        "raw_path": repo_relative(raw_path, output_root),
        "clean_text_path": repo_relative(clean_path, output_root),
        "translated_path": repo_relative(translated_path, output_root),
        "script_path": repo_relative(script_path, output_root),
        "segment_manifest_path": repo_relative(segment_manifest_path, output_root),
        "segment_count": len(segments),
        "tts_completed": len(completed_wavs),
        "audio": package_info,
    }


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
