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
        "ollama_cli": bool(shutil.which("ollama")),
        "ollama_running": _ollama_running(),
        "vibevoice_importable": importlib.util.find_spec("vibevoice") is not None,
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
