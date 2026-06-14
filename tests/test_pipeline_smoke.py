from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from web_to_podcast.config import load_config
from web_to_podcast.cli import main as cli_main
from web_to_podcast.doctor import collect_doctor_report
from web_to_podcast.extract import extract_readable_text
from web_to_podcast.pipeline import run_pipeline
from web_to_podcast.segments import split_tts_segment_specs
from web_to_podcast.sources import collect_sources
from web_to_podcast.sources import fetch_url
from web_to_podcast.status import inspect_run
from web_to_podcast.document import SourceDocument
import web_to_podcast.pipeline as pipeline_module
import web_to_podcast.sources as sources_module


class PipelineSmokeTest(unittest.TestCase):
    def test_extract_html(self) -> None:
        doc = SourceDocument.build(
            raw_text="<html><head><title>Ignore</title></head><body><h1>Hello</h1><script>x()</script><p>Readable text.</p></body></html>",
            source_url="https://example.com/hello",
            media_type="text/html",
        )
        title, text = extract_readable_text(doc)
        self.assertEqual(title, "Hello")
        self.assertIn("Readable text.", text)
        self.assertNotIn("x()", text)
        self.assertNotIn("Ignore", text)

    def test_auto_extractor_falls_back_to_basic(self) -> None:
        doc = SourceDocument.build(
            raw_text="<html><body><article><h1>Auto Title</h1><p>Body text.</p></article></body></html>",
            source_url="https://example.com/auto",
            media_type="text/html",
        )
        title, text = extract_readable_text(doc, extractor="auto")
        self.assertEqual(title, "Auto Title")
        self.assertIn("Body text.", text)

    def test_segments_include_pause_metadata(self) -> None:
        segments = split_tts_segment_specs("Title\n\nThis is one sentence. This is another sentence.", target_chars=30, max_chars=60)
        self.assertGreaterEqual(len(segments), 2)
        self.assertIn("pause_after_ms", segments[0])

    def test_pipeline_without_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = root / "article.md"
            article.write_text("# Demo\n\nA short local article for testing.", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"name": "test", "output_dir": str(root / "out")},
                        "source": {
                            "local_files": [
                                {"path": str(article), "title": "Demo", "section": "1. Demo", "order": 1}
                            ]
                        },
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            manifest = run_pipeline(config)
            out = root / "out"
            self.assertTrue((out / "manifest.json").exists())
            self.assertTrue((out / "02_clean_text").exists())
            self.assertTrue((out / "04_tts_script").exists())
            self.assertEqual(manifest["summary"]["documents"], 1)
            self.assertEqual(manifest["summary"]["audio_completed"], 0)
            status = inspect_run(out)
            self.assertTrue(status["ok"])
            strict_status = inspect_run(out, expect_audio=True)
            self.assertFalse(strict_status["ok"])
            self.assertEqual(cli_main(["status", "--output-dir", str(out)]), 0)
            self.assertEqual(cli_main(["status", "--output-dir", str(out), "--expect-audio"]), 1)

    def test_init_config_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "starter.yaml"
            exit_code = cli_main(["init-config", "--output", str(config_path), "--name", "starter", "--url", "https://example.com/a", "--title", "A"])
            self.assertEqual(exit_code, 0)
            cfg = load_config(config_path)
            self.assertEqual(cfg.project.name, "starter")
            self.assertEqual(cfg.source.urls[0]["url"], "https://example.com/a")

    def test_helper_scripts_are_executable(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for script in ["scripts/bootstrap.sh", "scripts/publish_github.sh"]:
            path = root / script
            self.assertTrue(path.exists(), script)
            self.assertTrue(os.access(path, os.X_OK), script)

    def test_config_aware_doctor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"output_dir": str(Path(tmp) / "out")},
                        "source": {"local_files": []},
                        "translation": {"enabled": True, "provider": "ollama", "model": "definitely-missing-model"},
                        "tts": {"enabled": True, "provider": "vibevoice", "voice_sample": str(Path(tmp) / "missing.wav")},
                    }
                ),
                encoding="utf-8",
            )
            report = collect_doctor_report(str(config_path), strict=True)
            self.assertFalse(report["ok"])
            self.assertIn("checks", report)
            self.assertTrue(any(issue["check"] in {"ollama_model", "voice_sample_exists"} for issue in report["issues"]))
            self.assertEqual(cli_main(["doctor", "--config", str(config_path), "--strict"]), 1)

    def test_config_parses_auth_and_rate_limit_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage_state = Path(tmp) / "state.json"
            storage_state.write_text("{}", encoding="utf-8")
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"output_dir": str(Path(tmp) / "out")},
                        "source": {
                            "headers": {"Authorization": "Bearer token"},
                            "storage_state": str(storage_state),
                            "request_delay_seconds": 0.25,
                        },
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            cfg = load_config(config_path)
            self.assertEqual(cfg.source.headers["Authorization"], "Bearer token")
            self.assertEqual(cfg.source.storage_state, str(storage_state))
            self.assertEqual(cfg.source.request_delay_seconds, 0.25)
            report = collect_doctor_report(str(config_path), strict=True)
            self.assertTrue(report["checks"]["storage_state_exists"]["ok"])

    def test_doctor_reports_trafilatura_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"output_dir": str(Path(tmp) / "out")},
                        "source": {"extractor": "trafilatura"},
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            report = collect_doctor_report(str(config_path), strict=True)
            self.assertIn("trafilatura_importable", report["checks"])

    def test_fetch_url_sends_custom_headers(self) -> None:
        recorded: dict[str, str] = {}

        class Headers(dict):
            def get_content_charset(self):
                return "utf-8"

        class Response:
            headers = Headers({"content-type": "text/html"})

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"<html>ok</html>"

        def fake_urlopen(request, timeout=0):
            for key, value in request.header_items():
                recorded[key.lower()] = value
            return Response()

        original_urlopen = sources_module.urllib.request.urlopen
        sources_module.urllib.request.urlopen = fake_urlopen
        try:
            text, content_type = fetch_url(
                "https://example.com",
                user_agent="CustomAgent",
                headers={"Authorization": "Bearer token"},
            )
        finally:
            sources_module.urllib.request.urlopen = original_urlopen
        self.assertIn("ok", text)
        self.assertEqual(content_type, "text/html")
        self.assertEqual(recorded["authorization"], "Bearer token")
        self.assertEqual(recorded["user-agent"], "CustomAgent")

    def test_phase_limited_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = root / "article.md"
            article.write_text("# Demo\n\nA short local article for phase testing.", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"name": "phase", "output_dir": str(root / "out")},
                        "source": {
                            "local_files": [
                                {"path": str(article), "title": "Demo", "section": "1. Demo", "order": 1}
                            ]
                        },
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            manifest = run_pipeline(config, to_phase="script")
            out = root / "out"
            self.assertEqual(manifest["to_phase"], "script")
            self.assertTrue((out / "04_tts_script").exists())
            self.assertFalse((out / "05_segments").exists())
            self.assertTrue(inspect_run(out)["ok"])

            manifest = run_pipeline(config, to_phase="segment", force=True)
            self.assertEqual(manifest["to_phase"], "segment")
            self.assertTrue((out / "05_segments").exists())
            self.assertTrue(inspect_run(out)["ok"])

    def test_late_phase_resume_uses_manifest_without_refetching_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = root / "article.md"
            article.write_text("# Demo\n\nResume without network.", encoding="utf-8")
            config_path = root / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"name": "resume", "output_dir": str(root / "out")},
                        "source": {
                            "local_files": [
                                {"path": str(article), "title": "Demo", "section": "1. Demo", "order": 1}
                            ]
                        },
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            run_pipeline(config, to_phase="script")

            original_collect_sources = pipeline_module.collect_sources
            pipeline_module.collect_sources = lambda _config: (_ for _ in ()).throw(RuntimeError("source collection should not run"))
            try:
                manifest = run_pipeline(config, from_phase="segment", to_phase="segment", force=True)
            finally:
                pipeline_module.collect_sources = original_collect_sources

            out = root / "out"
            self.assertTrue(manifest["resumed_from_manifest"])
            self.assertTrue((out / "05_segments").exists())
            self.assertTrue(inspect_run(out)["ok"])

    def test_static_html_selector_filters(self) -> None:
        html = """
        <html>
          <head><title>Page Title</title></head>
          <body>
            <nav>Navigation</nav>
            <main id="content"><h1>Article Title</h1><p>Keep me.</p><aside>Drop me.</aside></main>
            <footer>Footer</footer>
          </body>
        </html>
        """
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "project": {"output_dir": str(Path(tmp) / "out")},
                        "source": {
                            "content_selector": "#content",
                            "remove_selectors": ["aside"],
                            "urls": [{"url": "https://example.com/article", "order": 1}],
                        },
                        "translation": {"enabled": False},
                        "tts": {"enabled": False, "provider": "none"},
                    }
                ),
                encoding="utf-8",
            )
            config = load_config(config_path)
            original_fetch = sources_module.fetch_url
            sources_module.fetch_url = lambda *args, **kwargs: (html, "text/html")
            try:
                docs = collect_sources(config)
            finally:
                sources_module.fetch_url = original_fetch
            self.assertEqual(len(docs), 1)
            title, text = extract_readable_text(docs[0])
            self.assertEqual(title, "Article Title")
            self.assertIn("Keep me.", text)
            self.assertNotIn("Navigation", text)
            self.assertNotIn("Drop me.", text)
            self.assertNotIn("Footer", text)


if __name__ == "__main__":
    unittest.main()
