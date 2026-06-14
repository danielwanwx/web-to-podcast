from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .doctor import collect_doctor_report
from .pipeline import run_pipeline


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

    args = parser.parse_args(argv)
    if args.command == "doctor":
        print(json.dumps(collect_doctor_report(), ensure_ascii=False, indent=2))
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


if __name__ == "__main__":
    raise SystemExit(main())
