# VibeVoice Setup

VibeVoice is loaded lazily. You can use crawling, extraction, translation,
script rendering, segmentation, and status checks without importing a model.

For audio generation:

1. Install this project with TTS dependencies.

   ```bash
   scripts/bootstrap.sh --tts
   ```

2. Install VibeVoice in the same virtual environment if your environment does
   not already provide it.

3. Prepare a voice sample file. Any ffmpeg-readable audio or video can be used;
   the pipeline normalizes it to mono 24 kHz WAV in `00_voice/`.

4. Check the full workflow.

   ```bash
   web-to-podcast doctor --config my-resource.yaml --voice-sample /path/to/sample.wav --strict
   ```

5. Generate audio.

   ```bash
   web-to-podcast run --config my-resource.yaml --voice-sample /path/to/sample.wav
   web-to-podcast status --output-dir output/my-resource --expect-audio
   ```

Useful TTS config:

```yaml
tts:
  enabled: true
  provider: vibevoice
  voice_sample: /path/to/sample.wav
  device: mps
  isolate_process: true
  inference_steps: 5
  cfg_scale: 1.5
  sample_audio_leak_policy: trim
  sample_text_leak_policy: off
```

`isolate_process: true` is the recommended default for long batches because it
keeps each article generation in a subprocess and makes memory recovery more
predictable.
