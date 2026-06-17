# web-to-podcast

Reusable local-first pipeline for turning web resources and documents into
translated podcast audio.

Status: alpha developer tool. This project is intended for lawful personal,
internal, research, or archival workflows where you have the rights and
authorization needed to process the source material and any voice samples.

It is designed for the workflow we validated locally:

1. Crawl or import web pages and local documents.
2. Save raw source files and cleaned text.
3. Translate with a local Gemma model through Ollama.
4. Render a TTS-friendly narration script.
5. Split the script into short, pause-aware segments.
6. Generate audio with VibeVoice using an authorized local voice sample.
7. Package organized M4A files and a resumable manifest.

## Appropriate Use

Use this project only with content that you are allowed to access, copy,
transform, translate, and convert to audio. The repository does not include
scraped source pages, translations, generated audio, credentials, cookies, or
voice samples.

Do not use this project to bypass paywalls, access controls, rate limits, or
site terms; to redistribute copyrighted material without permission; to clone,
impersonate, or misrepresent a person's voice; or to publish private or
sensitive content without authorization.

This repository provides software and operational guardrails, not legal advice.
See [docs/legal-and-safety.md](docs/legal-and-safety.md) before using the
pipeline on third-party sites or voice samples.

## Quick Start

```bash
git clone <your-repo-url> web-to-podcast
cd web-to-podcast
scripts/bootstrap.sh
source .venv/bin/activate
web-to-podcast doctor
```

Run the offline smoke sample without translation or TTS:

```bash
web-to-podcast run --config examples/local_markdown.json
web-to-podcast status --output-dir output/local-smoke
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
web-to-podcast doctor --config examples/url_list.yaml --voice-sample /path/to/voice_sample.wav --strict
web-to-podcast run \
  --config examples/url_list.yaml \
  --voice-sample /path/to/voice_sample.wav
```

See [docs/vibevoice.md](docs/vibevoice.md) for the VibeVoice setup checklist.

Enable optional ASR-based sample text leakage checks only when needed:

```bash
pip install -e ".[asr]"
```

Enable browser rendering for JavaScript-heavy pages only when needed:

```bash
pip install -e ".[browser]"
python -m playwright install chromium
```

Enable stronger automatic article extraction only when needed:

```bash
pip install -e ".[extract]"
```

The bootstrap script has matching flags:

```bash
scripts/bootstrap.sh --browser
scripts/bootstrap.sh --extract
scripts/bootstrap.sh --tts
scripts/bootstrap.sh --asr
```

## Requirements

- Python 3.9 or newer.
- `ffmpeg` and `ffprobe` for audio packaging.
- Ollama running locally for Gemma translation.
- VibeVoice installed and a local VibeVoice model available for audio.

The default translation model is `gemma4:31b`. Change it in the config if your
local model name differs.

## Full Workflow Doctor

Before launching a long translation or audio job, run a config-aware check:

```bash
web-to-podcast doctor --config my-resource.yaml --voice-sample /path/to/sample.wav --strict
```

Strict mode returns a non-zero exit code if a configured dependency is missing,
such as the Ollama model, Playwright for browser-rendered pages, VibeVoice, or
the voice sample file.

## Make Targets

```bash
make bootstrap          # create .venv, install dev deps, run doctor and smoke
make bootstrap-browser  # also install Playwright Chromium
make bootstrap-extract  # also install trafilatura extraction support
make test
make doctor
make smoke
make clean
```

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
  extractor: basic
  # Use extractor: auto to try trafilatura when installed, then fallback.
  headers: {}
  storage_state: ""
  request_delay_seconds: 0
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

For large resources, run or regenerate the pipeline in phases:

```bash
# Stop after translation and inspect the local Chinese drafts.
web-to-podcast run --config my-resource.yaml --to-phase translate

# Stop after TTS scripts for manual review.
web-to-podcast run --config my-resource.yaml --to-phase script

# Regenerate only TTS/package stages from existing text artifacts.
web-to-podcast run --config my-resource.yaml --from-phase tts --force
```

Available phases are `source`, `extract`, `translate`, `script`, `segment`,
`tts`, and `package`.

When `--from-phase` is later than `source`, the pipeline first tries to resume
from the existing `manifest.json` and local stage files, so later-stage retries
do not need to fetch the website again.

## Run Status

Inspect a run directory at any time:

```bash
web-to-podcast status --output-dir output/my-resource
```

For production audio jobs, require every document to have a final audio file:

```bash
web-to-podcast status --output-dir output/my-resource --expect-audio
```

The status report checks `manifest.json`, each stage file, segment manifests,
failed or pending TTS chunks, and final audio paths.

## JavaScript Pages

For sites where the article is rendered after JavaScript runs, configure the
browser renderer and narrow extraction to the article body. Only use
authenticated browser state for accounts, content, and sites where you have
permission to automate access:

```yaml
source:
  renderer: playwright
  wait_until: networkidle
  storage_state: auth/state.json
  headers:
    Accept-Language: en-US,en;q=0.9
  request_delay_seconds: 0.5
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

`storage_state` is a Playwright storage-state JSON file. It is useful for pages
that require a logged-in browser session. Do not commit auth state files, and
do not use them to bypass access restrictions. See
[docs/authenticated-sites.md](docs/authenticated-sites.md) for a short setup
guide.

## Automatic Article Extraction

The built-in `basic` extractor is dependency-free and works well when you
configure `content_selector`. For unknown sites, install the optional extractor
and use `auto`:

```bash
pip install -e ".[extract]"
```

```yaml
source:
  extractor: auto
  urls:
    - url: https://example.com/article
      title: Article
      order: 1
```

`auto` tries `trafilatura` first and falls back to the built-in extractor.
Use `extractor: trafilatura` if you want missing trafilatura to fail loudly.

## Notes

The MIT license covers this software only. It does not grant rights to any
third-party content, website text, translated text, generated audio, voice
samples, model weights, or external tools used with the pipeline.

Before publishing a fork or public repository, review
[docs/open-source-checklist.md](docs/open-source-checklist.md).

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
