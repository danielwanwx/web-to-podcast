from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from web_to_podcast.config import load_config
from web_to_podcast.cli import main as cli_main
from web_to_podcast.extract import extract_readable_text
from web_to_podcast.pipeline import run_pipeline
from web_to_podcast.segments import split_tts_segment_specs
from web_to_podcast.sources import collect_sources
from web_to_podcast.status import inspect_run
from web_to_podcast.document import SourceDocument
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
