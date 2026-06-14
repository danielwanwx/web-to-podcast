# web-to-podcast

Reusable local pipeline for turning web resources into translated podcast audio.

It is designed for the workflow we validated locally:

1. Crawl or import web pages and local documents.
2. Save raw source files and cleaned text.
3. Translate with a local Gemma model through Ollama.
4. Render a TTS-friendly narration script.
5. Split the script into short, pause-aware segments.
6. Generate audio with VibeVoice using a local voice sample.
7. Package organized M4A files and a resumable manifest.

The project is not tied to HelloInterview. HelloInterview is only an example
configuration profile.

## Quick Start

```bash
git clone <your-repo-url> web-to-podcast
cd web-to-podcast
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
web-to-podcast doctor
```

Run the offline smoke sample without translation or TTS:

```bash
web-to-podcast run --config examples/local_markdown.json
```

Create a starter config for your own resource:

```bash
web-to-podcast init-config \
  --output my-resource.yaml \
  --name my-resource \
  --url https://example.com/article \
  --title "Article Title"
```

Run with Ollama translation and VibeVoice audio:

```bash
pip install -e ".[tts]"
web-to-podcast run \
  --config examples/url_list.yaml \
  --voice-sample /path/to/voice_sample.wav
```

Enable optional ASR-based sample text leakage checks only when needed:

```bash
pip install -e ".[asr]"
```

Enable browser rendering for JavaScript-heavy pages only when needed:

```bash
pip install -e ".[browser]"
python -m playwright install chromium
```

## Requirements

- Python 3.9 or newer.
- `ffmpeg` and `ffprobe` for audio packaging.
- Ollama running locally for Gemma translation.
- VibeVoice installed and a local VibeVoice model available for audio.

The default translation model is `gemma4:31b`. Change it in the config if your
local model name differs.

## Output Layout

Each run writes a self-contained output folder:

```text
output/
  01_sources/        raw HTML, Markdown, text, and source metadata
  02_clean_text/     extracted readable text
  03_translated/     translated documents and per-chunk cache
  04_tts_script/     narration scripts after symbol cleanup
  05_segments/       segment manifests and generated WAV chunks
  06_podcast/        final M4A files organized by section/title
  manifest.json      resumable run status
```

Generated content, samples, and caches are ignored by git.

## Config Shape

```yaml
project:
  name: my-resource
  output_dir: output/my-resource

source:
  renderer: static
  # Use renderer: playwright for JavaScript-heavy pages.
  # renderer: auto tries Playwright first, then falls back to static.
  content_selector: ""
  title_selector: ""
  remove_selectors: []
  max_scrolls: 0
  urls:
    - url: https://example.com/article-1
      title: Article 1
      section: "1. Foundations"
      order: 1
  crawl:
    start_urls: []
    max_pages: 0
    same_domain: true
    include_patterns: []
    exclude_patterns: []
  local_files: []

translation:
  enabled: true
  provider: ollama
  model: gemma4:31b
  target_language: zh

tts:
  enabled: true
  provider: vibevoice
  voice_sample: /path/to/sample.wav
  device: mps
  isolate_process: true
  sample_audio_leak_policy: trim
  sample_text_leak_policy: off
  sample_text_leak_phrases: ""

output:
  audio_format: m4a
  bitrate: 128k
  naming: official-title
```

## Resume Behavior

The pipeline writes every phase to disk. If a run stops halfway, rerun the same
command and completed files are reused. Add `--force` to regenerate.

## JavaScript Pages

For sites where the article is rendered after JavaScript runs, configure the
browser renderer and narrow extraction to the article body:

```yaml
source:
  renderer: playwright
  wait_until: networkidle
  content_selector: article
  title_selector: h1
  remove_selectors:
    - nav
    - footer
    - .sidebar
  max_scrolls: 2
  urls:
    - url: https://example.com/learn/topic/page
      title: Topic Page
      section: "1. Topic"
      order: 1
```

## Notes

Only use this pipeline for resources you are allowed to process. Voice samples
should be your own voice or voices you have permission to use.

## Publish To GitHub

This directory is a normal git repository. After creating an empty GitHub repo,
push it with:

```bash
git remote add origin git@github.com:<owner>/web-to-podcast.git
git push -u origin main
```

Or use the helper:

```bash
scripts/publish_github.sh git@github.com:<owner>/web-to-podcast.git
```

If GitHub CLI is installed and authenticated:

```bash
scripts/publish_github.sh --gh <owner>/web-to-podcast --private
```
