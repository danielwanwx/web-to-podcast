# Web to Podcast Spec

## Goal

Provide a cloneable repository that can convert many web/document resources into
local translated podcast audio without hard-coding one site.

## Non-goals

- Hosting generated content.
- Shipping copyrighted source pages, translations, or generated audio.
- Requiring a cloud TTS or cloud LLM.

## Pipeline Contract

Every stage is file-backed and resumable:

1. `source`: fetch URLs, crawl pages, or import local files.
2. `extract`: remove boilerplate and produce stable readable text.
3. `translate`: chunk source text and translate through Ollama.
4. `script`: remove Markdown, code fences, symbols, and mechanical punctuation.
5. `segment`: split narration into short chunks with pause metadata.
6. `tts`: synthesize WAV segments with VibeVoice.
7. `package`: concatenate with natural pauses and encode M4A.

## Extension Points

- Add new source providers under `web_to_podcast/sources.py`.
- Add extraction backends under `web_to_podcast/extract.py`.
- Add translator providers under `web_to_podcast/translate.py`.
- Add TTS providers under `web_to_podcast/tts.py`.
- Add site-specific ordering by supplying `title`, `section`, and `order` in
  config, not by changing pipeline code.

## Guardrails

- Generated audio and voice samples are ignored by git.
- VibeVoice imports are lazy so normal crawl/translation tests do not load a
  model.
- Audio generation can run in an isolated subprocess to release model memory
  between articles.
- Reference-sample audio leakage is checked and trimmed/rejected when enabled.
