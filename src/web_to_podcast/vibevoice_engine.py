from __future__ import annotations

import os
from pathlib import Path

from .script import render_tts_script
from .voice_guard import VoiceSampleLeakConfig, VoiceSampleLeakGuard, VoiceSampleTextLeakConfig, VoiceSampleTextLeakGuard


DEFAULT_VIBEVOICE_MODEL_ID = "microsoft/VibeVoice-1.5B"


class VibeVoiceEngine:
    """Lazy VibeVoice wrapper used by the standalone pipeline."""

    def __init__(
        self,
        *,
        model_path: str = "",
        device: str = "mps",
        inference_steps: int = 5,
        cfg_scale: float = 1.5,
        max_new_tokens: int = 220,
        max_length_times: float = 1.2,
        voice_sample: str = "",
        sample_audio_leak_policy: str = "trim",
        sample_audio_leak_corr_threshold: float = 0.88,
        sample_audio_leak_audit_path: str = "",
        sample_text_leak_policy: str = "off",
        sample_text_leak_phrases: str = "",
        sample_text_leak_audit_path: str = "",
    ) -> None:
        self.model_path = model_path or default_vibevoice_model_path()
        self.device = device
        self.inference_steps = inference_steps
        self.cfg_scale = cfg_scale
        self.max_new_tokens = max_new_tokens
        self.max_length_times = max_length_times
        self.voice_sample = voice_sample
        self.sample_audio_leak_policy = sample_audio_leak_policy
        self.sample_audio_leak_corr_threshold = sample_audio_leak_corr_threshold
        self.sample_audio_leak_audit_path = sample_audio_leak_audit_path
        self.sample_text_leak_policy = sample_text_leak_policy
        self.sample_text_leak_phrases = sample_text_leak_phrases
        self.sample_text_leak_audit_path = sample_text_leak_audit_path
        self._processor = None
        self._model = None
        self._loaded = False
        self._leak_guard = None
        self._text_leak_guard = None

    def load(self) -> None:
        if self._loaded:
            return
        import torch
        from vibevoice.modular.modeling_vibevoice_inference import VibeVoiceForConditionalGenerationInference
        from vibevoice.processor.vibevoice_processor import VibeVoiceProcessor

        self._processor = VibeVoiceProcessor.from_pretrained(self.model_path)
        self._model = VibeVoiceForConditionalGenerationInference.from_pretrained(
            self.model_path,
            torch_dtype=torch.bfloat16,
            device_map=self.device,
        )
        self._model.eval()
        if hasattr(self._model, "set_ddpm_inference_steps"):
            self._model.set_ddpm_inference_steps(self.inference_steps)
        self._loaded = True

    def synthesize_to_file(self, text: str, output_path: Path | str, *, segment_id: str = "", attempt: int = 1) -> bool:
        audio, sample_rate = self.generate_audio(text)
        if audio is None:
            return False
        guard = self._sample_leak_guard(sample_rate)
        if guard:
            audio, _ = guard.sanitize(audio, segment_id=segment_id, attempt=attempt)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        try:
            import soundfile as sf

            sf.write(str(output), audio, sample_rate)
        except ImportError:
            import numpy as np
            from scipy.io import wavfile

            wavfile.write(str(output), sample_rate, (audio * 32767).astype(np.int16))
        text_guard = self._sample_text_leak_guard()
        if text_guard:
            try:
                text_guard.assert_clean_file(output, segment_id=segment_id, attempt=attempt)
            except Exception:
                try:
                    output.unlink()
                except OSError:
                    pass
                raise
        return True

    def generate_audio(self, text: str):
        self.load()
        import torch

        assert self._processor is not None
        assert self._model is not None

        clean_text, _ = render_tts_script(text)
        script = f"Speaker 1: {clean_text}"
        voice_args = {}
        if self.voice_sample:
            voice_args["voice_samples"] = [self.voice_sample]
        inputs = self._processor(text=script, **voice_args, return_tensors="pt")
        model_inputs = {}
        for key, value in inputs.items():
            if isinstance(value, torch.Tensor):
                model_inputs[key] = value.to(self._model.device)
            elif value is not None:
                model_inputs[key] = value

        if model_inputs.get("speech_tensors") is None:
            device = self._model.device
            model_inputs["speech_tensors"] = torch.zeros(1, 3200, dtype=torch.bfloat16, device=device)
            model_inputs["speech_masks"] = torch.zeros(1, 1, dtype=torch.bool, device=device)

        kwargs = {
            **model_inputs,
            "cfg_scale": self.cfg_scale,
            "tokenizer": self._processor.tokenizer,
            "max_new_tokens": self.max_new_tokens,
        }
        if self.max_length_times:
            kwargs["max_length_times"] = self.max_length_times
        with torch.no_grad():
            output = self._model.generate(**kwargs)
        if not output.speech_outputs or output.speech_outputs[0] is None:
            return None, 24000
        audio = output.speech_outputs[0][0].float().cpu().numpy()
        return audio, 24000

    def _sample_leak_guard(self, sample_rate: int):
        if self.sample_audio_leak_policy == "off" or not self.voice_sample:
            return None
        if self._leak_guard is None:
            self._leak_guard = VoiceSampleLeakGuard(
                self.voice_sample,
                sample_rate=sample_rate,
                config=VoiceSampleLeakConfig(
                    policy=self.sample_audio_leak_policy,
                    corr_threshold=self.sample_audio_leak_corr_threshold,
                    audit_path=self.sample_audio_leak_audit_path or None,
                ),
            )
        return self._leak_guard if getattr(self._leak_guard, "profile", None) else None

    def _sample_text_leak_guard(self):
        if self.sample_text_leak_policy == "off" or not self.sample_text_leak_phrases.strip():
            return None
        if self._text_leak_guard is None:
            self._text_leak_guard = VoiceSampleTextLeakGuard(
                VoiceSampleTextLeakConfig(
                    policy=self.sample_text_leak_policy,
                    phrases=self.sample_text_leak_phrases,
                    audit_path=self.sample_text_leak_audit_path or None,
                )
            )
        return self._text_leak_guard if getattr(self._text_leak_guard, "markers", None) else None


def default_vibevoice_model_path() -> str:
    configured = os.getenv("VIBEVOICE_MODEL_PATH", "").strip()
    if configured:
        return configured
    candidates = [
        Path.home() / ".cache" / "huggingface" / "hub" / "models--microsoft--VibeVoice-1.5B" / "snapshots",
        Path.home() / ".cache" / "huggingface" / "hub" / "models--vibevoice--VibeVoice-1.5B" / "snapshots",
    ]
    for cache_root in candidates:
        if cache_root.exists():
            snapshots = sorted(
                (path for path in cache_root.iterdir() if path.is_dir()),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            if snapshots:
                return str(snapshots[0])
    return DEFAULT_VIBEVOICE_MODEL_ID
