from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import PipelineConfig, load_config
from .vibevoice_engine import default_vibevoice_model_path


def collect_doctor_report(
    config_path: str | None = None,
    *,
    voice_sample: str = "",
    strict: bool = False,
) -> dict[str, Any]:
    config = load_config(config_path) if config_path else None
    if config and voice_sample:
        config.tts.voice_sample = voice_sample
    report: dict[str, Any] = {
        "python": platform.python_version(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "git": bool(shutil.which("git")),
        "gh_cli": bool(shutil.which("gh")),
        "ollama_cli": bool(shutil.which("ollama")),
        "ollama_running": _ollama_running(),
        "ollama_models": _ollama_models(),
        "vibevoice_importable": importlib.util.find_spec("vibevoice") is not None,
        "vibevoice_model_path": default_vibevoice_model_path(),
        "vibevoice_model_available": _vibevoice_model_available(default_vibevoice_model_path()),
        "playwright_importable": importlib.util.find_spec("playwright") is not None,
        "github_remote": _git_remote_origin(),
        "config_path": str(config_path or ""),
        "strict": bool(strict),
        "checks": {},
        "issues": [],
        "ready": True,
        "ok": True,
    }
    _add_base_checks(report)
    if config:
        _add_config_checks(report, config)
    report["ready"] = not report["issues"]
    report["ok"] = report["ready"] if strict else True
    return report


def _add_base_checks(report: dict[str, Any]) -> None:
    _record_check(report, "python", True, f"Python {report['python']}")
    _record_check(report, "ffmpeg", bool(report["ffmpeg"]), "ffmpeg is available", "ffmpeg is required for audio packaging")
    _record_check(report, "ffprobe", bool(report["ffprobe"]), "ffprobe is available", "ffprobe is required for audio status inspection")


def _ollama_running() -> bool:
    ollama = shutil.which("ollama")
    if not ollama:
        return False
    try:
        result = subprocess.run([ollama, "ps"], text=True, capture_output=True, check=False, timeout=5)
    except Exception:
        return False
    return result.returncode == 0


def _ollama_models() -> list[str]:
    ollama = shutil.which("ollama")
    if not ollama:
        return []
    try:
        result = subprocess.run([ollama, "list"], text=True, capture_output=True, check=False, timeout=10)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    models: list[str] = []
    for line in (result.stdout or "").splitlines()[1:]:
        if not line.strip():
            continue
        models.append(line.split()[0])
    return models


def _git_remote_origin() -> str:
    if not shutil.which("git"):
        return ""
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], text=True, capture_output=True, check=False, timeout=5)
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _add_config_checks(report: dict[str, Any], config: PipelineConfig) -> None:
    renderer = (config.source.renderer or "static").lower()
    if renderer in {"playwright", "browser"}:
        _record_check(report, "playwright_importable", bool(report["playwright_importable"]), "Playwright package is importable", "Playwright renderer requested but playwright is not installed")
    elif renderer == "auto":
        _record_check(report, "playwright_importable_optional", True, "auto renderer can fall back to static fetching")
    if config.source.storage_state:
        storage_state_path = _config_relative_path(config.source.storage_state, config)
        _record_check(
            report,
            "storage_state_exists",
            storage_state_path.exists(),
            f"Playwright storage state exists: {storage_state_path}",
            f"Playwright storage state file does not exist: {storage_state_path}",
        )

    if config.translation.enabled and config.translation.provider == "ollama":
        _record_check(report, "ollama_cli", bool(report["ollama_cli"]), "Ollama CLI is available", "Ollama CLI is required for local Gemma translation")
        _record_check(report, "ollama_running", bool(report["ollama_running"]), "Ollama is running", "Ollama must be running for translation")
        model_available = config.translation.model in set(report.get("ollama_models") or [])
        _record_check(
            report,
            "ollama_model",
            model_available,
            f"Ollama model {config.translation.model!r} is available",
            f"Ollama model {config.translation.model!r} is not installed; run: ollama pull {config.translation.model}",
        )

    if config.tts.enabled and config.tts.provider == "vibevoice":
        _record_check(report, "vibevoice_importable", bool(report["vibevoice_importable"]), "VibeVoice package is importable", "VibeVoice package is not importable in this environment")
        _record_check(report, "vibevoice_model_available", bool(report["vibevoice_model_available"]), "VibeVoice model path is available locally", "VibeVoice model path is not local; first run may download from Hugging Face")
        sample = (config.tts.voice_sample or "").strip()
        _record_check(report, "voice_sample_configured", bool(sample), "voice_sample is configured", "TTS is enabled but no voice_sample is configured")
        if sample:
            _record_check(report, "voice_sample_exists", Path(sample).expanduser().exists(), f"voice sample exists: {sample}", f"voice sample does not exist: {sample}")


def _record_check(report: dict[str, Any], name: str, ok: bool, success_message: str, failure_message: str | None = None) -> None:
    message = success_message if ok else (failure_message or success_message)
    report["checks"][name] = {"ok": bool(ok), "message": message}
    if not ok:
        report["issues"].append({"check": name, "message": message})


def _vibevoice_model_available(model_path: str) -> bool:
    if not model_path:
        return False
    if model_path.startswith(("http://", "https://")):
        return False
    if "/" in model_path and not model_path.startswith(("/", "~", ".")):
        return False
    return Path(os.path.expanduser(model_path)).exists()


def _config_relative_path(value: str, config: PipelineConfig) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    if config.config_path:
        return config.config_path.parent / path
    return path
