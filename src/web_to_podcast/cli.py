from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .doctor import collect_doctor_report
from .pipeline import run_pipeline
from .status import inspect_run
from .utils import slugify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="web-to-podcast")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the full source-to-podcast pipeline.")
    run_parser.add_argument("--config", required=True, help="Path to JSON/YAML config.")
    run_parser.add_argument("--voice-sample", default="", help="Override VibeVoice sample path.")
    run_parser.add_argument("--output-dir", default="", help="Override output directory.")
    run_parser.add_argument("--force", action="store_true", help="Regenerate cached phase outputs.")
    run_parser.add_argument("--dry-run", action="store_true", help="Disable translation and TTS; useful for smoke tests.")

    subparsers.add_parser("doctor", help="Check local runtime dependencies.")

    status_parser = subparsers.add_parser("status", help="Inspect a run output directory.")
    status_parser.add_argument("--output-dir", required=True, help="Pipeline output directory containing manifest.json.")
    status_parser.add_argument("--expect-audio", action="store_true", help="Fail if final audio is missing or skipped.")

    init_parser = subparsers.add_parser("init-config", help="Write a starter config file.")
    init_parser.add_argument("--output", default="web-to-podcast.yaml", help="Config path to create.")
    init_parser.add_argument("--name", default="my-resource", help="Project name.")
    init_parser.add_argument("--url", default="https://example.com/", help="First URL to include.")
    init_parser.add_argument("--title", default="Example Article", help="First article title.")

    args = parser.parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(collect_doctor_report(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "status":
        report = inspect_run(args.output_dir, expect_audio=args.expect_audio)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1
    if args.command == "init-config":
        output = Path(args.output)
        if output.exists():
            raise SystemExit(f"config already exists: {output}")
        output.write_text(_starter_config(args.name, args.url, args.title), encoding="utf-8")
        print(str(output))
        return 0
    if args.command == "run":
        config = load_config(args.config)
        if args.voice_sample:
            config.tts.voice_sample = args.voice_sample
        if args.output_dir:
            config.project.output_dir = args.output_dir
        if args.dry_run:
            config.translation.enabled = False
            config.tts.enabled = False
            config.tts.provider = "none"
        manifest = run_pipeline(config, force=args.force)
        manifest_path = Path(config.project.output_dir).expanduser() / "manifest.json"
        summary = manifest.get("summary", {})
        print(json.dumps({"manifest": str(manifest_path), "summary": summary}, ensure_ascii=False, indent=2))
        return 0
    return 2


def _starter_config(name: str, url: str, title: str) -> str:
    project_slug = slugify(name, "my-resource")
    return f"""project:
  name: {_yaml_string(name)}
  output_dir: {_yaml_string(f"output/{project_slug}")}

source:
  renderer: static
  # Use renderer: playwright for JavaScript-heavy pages.
  # content_selector: article
  # title_selector: h1
  # remove_selectors: ["nav", "footer", ".sidebar"]
  urls:
    - url: {_yaml_string(url)}
      title: {_yaml_string(title)}
      section: "1. Articles"
      order: 1

translation:
  enabled: true
  provider: ollama
  model: gemma4:31b
  target_language: zh
  chunk_chars: 2800

tts:
  enabled: true
  provider: vibevoice
  voice_sample: ""
  device: mps
  isolate_process: true
  sample_audio_leak_policy: trim
  sample_text_leak_policy: off

output:
  naming: official-title
  audio_format: m4a
  bitrate: 128k
"""


def _yaml_string(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


if __name__ == "__main__":
    raise SystemExit(main())
