from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
from typing import Any


def collect_doctor_report() -> dict[str, Any]:
    return {
        "python": platform.python_version(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "ffprobe": bool(shutil.which("ffprobe")),
        "git": bool(shutil.which("git")),
        "gh_cli": bool(shutil.which("gh")),
        "ollama_cli": bool(shutil.which("ollama")),
        "ollama_running": _ollama_running(),
        "vibevoice_importable": importlib.util.find_spec("vibevoice") is not None,
        "playwright_importable": importlib.util.find_spec("playwright") is not None,
        "github_remote": _git_remote_origin(),
    }


def _ollama_running() -> bool:
    ollama = shutil.which("ollama")
    if not ollama:
        return False
    try:
        result = subprocess.run([ollama, "ps"], text=True, capture_output=True, check=False, timeout=5)
    except Exception:
        return False
    return result.returncode == 0


def _git_remote_origin() -> str:
    if not shutil.which("git"):
        return ""
    try:
        result = subprocess.run(["git", "remote", "get-url", "origin"], text=True, capture_output=True, check=False, timeout=5)
    except Exception:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""
