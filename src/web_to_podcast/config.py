from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .utils import coerce_list


@dataclass
class CrawlConfig:
    start_urls: list[str] = field(default_factory=list)
    max_pages: int = 0
    same_domain: bool = True
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class SourceConfig:
    urls: list[Any] = field(default_factory=list)
    url_file: str = ""
    sitemap_urls: list[str] = field(default_factory=list)
    local_files: list[Any] = field(default_factory=list)
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    renderer: str = "static"
    extractor: str = "basic"
    wait_until: str = "networkidle"
    content_selector: str = ""
    title_selector: str = ""
    remove_selectors: list[str] = field(default_factory=list)
    max_scrolls: int = 0
    headers: dict[str, str] = field(default_factory=dict)
    storage_state: str = ""
    request_delay_seconds: float = 0.0
    timeout_seconds: int = 30
    user_agent: str = "web-to-podcast/0.1"


@dataclass
class TranslationConfig:
    enabled: bool = True
    provider: str = "ollama"
    model: str = "gemma4:31b"
    target_language: str = "zh"
    chunk_chars: int = 2800
    timeout_seconds: int = 900
    retries: int = 2


@dataclass
class TTSConfig:
    enabled: bool = True
    provider: str = "vibevoice"
    model_path: str = ""
    device: str = "mps"
    voice_sample: str = ""
    isolate_process: bool = True
    inference_steps: int = 5
    cfg_scale: float = 1.5
    max_new_tokens: int = 220
    max_length_times: float = 1.2
    timeout_seconds: int = 1800
    retries: int = 2
    target_chars: int = 80
    max_chars: int = 120
    sample_audio_leak_policy: str = "trim"
    sample_audio_leak_corr_threshold: float = 0.88
    sample_text_leak_policy: str = "off"
    sample_text_leak_phrases: str = ""


@dataclass
class OutputConfig:
    naming: str = "official-title"
    audio_format: str = "m4a"
    bitrate: str = "128k"
    keep_wav: bool = False


@dataclass
class ProjectConfig:
    name: str = "web-to-podcast"
    output_dir: str = "output/web-to-podcast"


@dataclass
class PipelineConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    translation: TranslationConfig = field(default_factory=TranslationConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    config_path: Path | None = None


def load_config(path: Path | str) -> PipelineConfig:
    config_path = Path(path)
    raw = _load_mapping(config_path)
    cfg = PipelineConfig(
        project=_project_config(raw.get("project") or {}),
        source=_source_config(raw.get("source") or {}),
        translation=_translation_config(raw.get("translation") or {}),
        tts=_tts_config(raw.get("tts") or {}),
        output=_output_config(raw.get("output") or {}),
        config_path=config_path,
    )
    return cfg


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError("PyYAML is required to read YAML config files") from exc
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("config file must contain a mapping")
    return data


def _project_config(data: dict[str, Any]) -> ProjectConfig:
    return ProjectConfig(
        name=str(data.get("name") or "web-to-podcast"),
        output_dir=str(data.get("output_dir") or "output/web-to-podcast"),
    )


def _source_config(data: dict[str, Any]) -> SourceConfig:
    crawl_data = data.get("crawl") or {}
    if not isinstance(crawl_data, dict):
        crawl_data = {}
    return SourceConfig(
        urls=coerce_list(data.get("urls")),
        url_file=str(data.get("url_file") or ""),
        sitemap_urls=[str(item) for item in coerce_list(data.get("sitemap_urls"))],
        local_files=coerce_list(data.get("local_files")),
        crawl=CrawlConfig(
            start_urls=[str(item) for item in coerce_list(crawl_data.get("start_urls"))],
            max_pages=int(crawl_data.get("max_pages") or 0),
            same_domain=bool(crawl_data.get("same_domain", True)),
            include_patterns=[str(item) for item in coerce_list(crawl_data.get("include_patterns"))],
            exclude_patterns=[str(item) for item in coerce_list(crawl_data.get("exclude_patterns"))],
        ),
        renderer=str(data.get("renderer") or "static"),
        extractor=str(data.get("extractor") or "basic"),
        wait_until=str(data.get("wait_until") or "networkidle"),
        content_selector=str(data.get("content_selector") or ""),
        title_selector=str(data.get("title_selector") or ""),
        remove_selectors=[str(item) for item in coerce_list(data.get("remove_selectors"))],
        max_scrolls=int(data.get("max_scrolls") or 0),
        headers=_string_mapping(data.get("headers") or {}),
        storage_state=str(data.get("storage_state") or ""),
        request_delay_seconds=float(data.get("request_delay_seconds") or 0),
        timeout_seconds=int(data.get("timeout_seconds") or 30),
        user_agent=str(data.get("user_agent") or "web-to-podcast/0.1"),
    )


def _string_mapping(data: Any) -> dict[str, str]:
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items()}


def _translation_config(data: dict[str, Any]) -> TranslationConfig:
    return TranslationConfig(
        enabled=bool(data.get("enabled", True)),
        provider=str(data.get("provider") or "ollama"),
        model=str(data.get("model") or "gemma4:31b"),
        target_language=str(data.get("target_language") or "zh"),
        chunk_chars=int(data.get("chunk_chars") or 2800),
        timeout_seconds=int(data.get("timeout_seconds") or 900),
        retries=int(data.get("retries") or 2),
    )


def _tts_config(data: dict[str, Any]) -> TTSConfig:
    return TTSConfig(
        enabled=bool(data.get("enabled", True)),
        provider=str(data.get("provider") or "vibevoice"),
        model_path=str(data.get("model_path") or ""),
        device=str(data.get("device") or "mps"),
        voice_sample=str(data.get("voice_sample") or ""),
        isolate_process=bool(data.get("isolate_process", True)),
        inference_steps=int(data.get("inference_steps") or 5),
        cfg_scale=float(data.get("cfg_scale") or 1.5),
        max_new_tokens=int(data.get("max_new_tokens") or 220),
        max_length_times=float(data.get("max_length_times") or 1.2),
        timeout_seconds=int(data.get("timeout_seconds") or 1800),
        retries=int(data.get("retries") or 2),
        target_chars=int(data.get("target_chars") or 80),
        max_chars=int(data.get("max_chars") or 120),
        sample_audio_leak_policy=str(data.get("sample_audio_leak_policy") or "trim"),
        sample_audio_leak_corr_threshold=float(data.get("sample_audio_leak_corr_threshold") or 0.88),
        sample_text_leak_policy=str(data.get("sample_text_leak_policy") or "off"),
        sample_text_leak_phrases=str(data.get("sample_text_leak_phrases") or ""),
    )


def _output_config(data: dict[str, Any]) -> OutputConfig:
    return OutputConfig(
        naming=str(data.get("naming") or "official-title"),
        audio_format=str(data.get("audio_format") or "m4a"),
        bitrate=str(data.get("bitrate") or "128k"),
        keep_wav=bool(data.get("keep_wav", False)),
    )
