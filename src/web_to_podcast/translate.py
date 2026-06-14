from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib import request as urlrequest

from .config import TranslationConfig
from .utils import write_text


def translation_prompt(title: str, chunk: str, index: int, total: int, target_language: str = "zh") -> str:
    if target_language.lower().startswith("zh"):
        return f"""你是一名严谨的技术内容译者和有声稿编辑。

请把下面英文内容翻译成适合直接朗读的中文稿。

要求：
- 忠实保留原文含义、论证顺序和技术术语。
- 不要添加原文没有的解释、标题、总结或寒暄。
- 不要输出 Markdown 符号、脚注编号、代码围栏或项目符号。
- 缩写和专有名词保持自然，必要时保留英文。
- 只输出译文正文。

文档：{title}
分段：{index}/{total}

英文原文：
{chunk}
"""
    return f"""Translate the following document chunk into {target_language}.

Keep the original meaning and order. Output only the translated body.

Document: {title}
Chunk: {index}/{total}

Source:
{chunk}
"""


def translate_document(
    title: str,
    text: str,
    out_dir: Path,
    config: TranslationConfig,
    *,
    force: bool = False,
) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    final_path = out_dir / "translated.md"
    if final_path.exists() and not force:
        return final_path.read_text(encoding="utf-8")
    if not config.enabled or config.provider == "none":
        write_text(final_path, text.strip() + "\n")
        return text.strip()
    if config.provider != "ollama":
        raise ValueError(f"unsupported translation provider: {config.provider}")

    chunks = split_translation_chunks(text, target_chars=config.chunk_chars)
    translated: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        chunk_path = out_dir / f"chunk_{index:04d}.md"
        if chunk_path.exists() and not force:
            translated.append(chunk_path.read_text(encoding="utf-8").strip())
            continue
        prompt = translation_prompt(title, chunk, index, len(chunks), config.target_language)
        output = run_ollama(config.model, prompt, timeout=config.timeout_seconds, retries=config.retries)
        write_text(chunk_path, output.strip() + "\n")
        translated.append(output.strip())
    final = "\n\n".join(part for part in translated if part).strip()
    write_text(final_path, final + "\n")
    return final


def split_translation_chunks(text: str, target_chars: int = 2800) -> list[str]:
    target = max(800, int(target_chars))
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs or [text.strip()]:
        if len(paragraph) > target:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_hard_split(paragraph, target))
            continue
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if current and len(candidate) > target:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def run_ollama(model: str, prompt: str, timeout: int = 900, retries: int = 2) -> str:
    attempts = max(1, retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            _wait_for_ollama_not_unloading(model)
            if os.getenv("WEB_TO_PODCAST_OLLAMA_USE_CLI", "").strip() == "1":
                return _run_ollama_cli(model, prompt, timeout)
            return _run_ollama_http(model, prompt, timeout)
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2 * attempt, 10))
    raise RuntimeError(f"ollama translation failed with model {model}: {last_error}")


def _run_ollama_http(model: str, prompt: str, timeout: int) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": os.getenv("WEB_TO_PODCAST_OLLAMA_KEEP_ALIVE", "10m"),
    }
    req = urlrequest.Request(
        _ollama_generate_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlrequest.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if parsed.get("error"):
        raise RuntimeError(str(parsed["error"]))
    output = str(parsed.get("response") or "").strip()
    if not output:
        raise RuntimeError("ollama returned no generated text")
    return output


def _run_ollama_cli(model: str, prompt: str, timeout: int) -> str:
    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    message = result.stderr.strip() or result.stdout.strip() or "ollama returned no output"
    raise RuntimeError(message)


def _ollama_generate_url() -> str:
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/") + "/api/generate"


def _wait_for_ollama_not_unloading(model: str) -> None:
    wait_seconds = float(os.getenv("WEB_TO_PODCAST_OLLAMA_UNLOADING_WAIT", "180"))
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        state = _ollama_model_state(model)
        if not state.get("unloading"):
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(f"ollama model {model} is still stopping")
        time.sleep(2)


def _ollama_model_state(model: str) -> dict[str, str | bool]:
    ollama = shutil.which("ollama")
    if not ollama:
        return {}
    try:
        result = subprocess.run([ollama, "ps"], text=True, capture_output=True, check=False, timeout=10)
    except Exception:
        return {}
    if result.returncode != 0:
        return {}
    for line in (result.stdout or "").splitlines()[1:]:
        if not line.strip():
            continue
        parts = line.split()
        if parts and parts[0] == model:
            return {"name": parts[0], "unloading": "stopping" in line.lower()}
    return {}


def _hard_split(text: str, max_chars: int) -> list[str]:
    return [text[index : index + max_chars].strip() for index in range(0, len(text), max_chars) if text[index : index + max_chars].strip()]
