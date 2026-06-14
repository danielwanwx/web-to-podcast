from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import unicodedata


@dataclass(frozen=True)
class VoiceSampleLeakConfig:
    policy: str = "trim"
    corr_threshold: float = 0.88
    signature_seconds: float = 3.0
    edge_seconds: float = 1.5
    min_remaining_seconds: float = 0.7
    audit_path: str | None = None


class VoiceSampleLeakGuard:
    """Detect accidental inclusion of the reference sample waveform."""

    def __init__(self, voice_sample: str | None, sample_rate: int = 24000, config: VoiceSampleLeakConfig | None = None):
        self.voice_sample = voice_sample or ""
        self.sample_rate = sample_rate
        self.config = config or VoiceSampleLeakConfig()
        self.profile: dict[str, Any] | None = None
        self.disabled_reason = ""
        if not self.voice_sample or self.config.policy == "off":
            return
        try:
            import soundfile as sf

            self.profile = load_voice_reference_profile(
                Path(self.voice_sample),
                sf,
                sample_rate,
                self.config.signature_seconds,
            )
        except Exception as exc:
            self.disabled_reason = f"voice reference profile failed: {exc}"

    def sanitize(self, audio: object, *, segment_id: str | int = "", attempt: int = 1):
        import numpy as np

        audio_arr = np.asarray(audio, dtype=np.float32)
        if not self.profile or self.config.policy == "off":
            return audio_arr, None
        leak = detect_voice_sample_leak(audio_arr, self.profile, self.config.corr_threshold, self.config.edge_seconds)
        if not leak:
            return audio_arr, None

        event = {
            "segment": segment_id,
            "attempt": attempt,
            **leak,
            "policy": self.config.policy,
            "original_samples": int(len(audio_arr)),
        }
        if self.config.policy == "error" or leak["position"] == "middle":
            self._append_audit({**event, "action": "reject"})
            raise RuntimeError(f"voice sample leakage detected: {leak}")

        if leak["position"] == "start":
            sanitized = audio_arr[int(leak["clamped_end"]) :]
        else:
            sanitized = audio_arr[: int(leak["clamped_start"])]
        min_remaining = int(self.config.min_remaining_seconds * int(self.profile["sample_rate"]))
        if len(sanitized) < min_remaining:
            self._append_audit({**event, "action": "reject_too_short", "remaining_samples": int(len(sanitized))})
            raise RuntimeError(f"voice sample leakage left too little audio: {leak}")
        self._append_audit({**event, "action": "trim", "remaining_samples": int(len(sanitized))})
        return sanitized.astype(np.float32), leak

    def _append_audit(self, event: dict[str, Any]) -> None:
        if not self.config.audit_path:
            return
        path = Path(self.config.audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **event}, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class VoiceSampleTextLeakConfig:
    policy: str = "off"
    phrases: str = ""
    min_match_chars: int = 8
    min_hits: int = 2
    asr_model: str = "small"
    asr_device: str = "cpu"
    asr_language: str = "zh"
    audit_path: str | None = None


class VoiceSampleTextLeakGuard:
    """Optional ASR-based check for generated speech repeating sample text."""

    def __init__(self, config: VoiceSampleTextLeakConfig | None = None):
        self.config = config or VoiceSampleTextLeakConfig()
        self.markers = build_sample_text_markers(parse_sample_text_leak_phrases(self.config.phrases), self.config.min_match_chars)
        self._model = None

    def assert_clean_file(self, audio_path: Path | str, *, segment_id: str | int = "", attempt: int = 1) -> None:
        if self.config.policy == "off" or not self.markers:
            return
        transcript = self._transcribe_file(Path(audio_path))
        leak = detect_sample_text_leak_from_transcript(transcript, self.markers, min_hits=self.config.min_hits)
        if not leak:
            return
        event = {
            "segment": segment_id,
            "attempt": attempt,
            "policy": self.config.policy,
            "action": "reject_text_leak",
            **leak,
        }
        self._append_audit(event)
        raise RuntimeError(f"voice sample text leakage detected: {leak.get('matched_markers')}")

    def _transcribe_file(self, audio_path: Path) -> str:
        model = self._load_model()
        result = model.transcribe(str(audio_path), language=self.config.asr_language or None, fp16=False, verbose=False)
        return str(result.get("text") or "").strip()

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        import whisper

        self._model = whisper.load_model(self.config.asr_model, device=self.config.asr_device)
        return self._model

    def _append_audit(self, event: dict[str, Any]) -> None:
        if not self.config.audit_path:
            return
        path = Path(self.config.audit_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), **event}, ensure_ascii=False) + "\n")


def parse_sample_text_leak_phrases(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[|\n]+", raw or "") if item.strip()]


def build_sample_text_markers(phrases: list[str], min_match_chars: int = 8) -> list[str]:
    width = max(4, int(min_match_chars))
    step = max(1, width // 2)
    markers: list[str] = []
    seen: set[str] = set()
    for phrase in phrases:
        normalized = normalize_text_for_leak_detection(phrase)
        if len(normalized) < width:
            continue
        candidates = [normalized] if len(normalized) <= width * 2 else []
        if len(normalized) > width:
            candidates.extend(normalized[offset : offset + width] for offset in range(0, len(normalized) - width + 1, step))
            candidates.append(normalized[-width:])
        else:
            candidates.append(normalized)
        for candidate in candidates:
            if len(candidate) >= width and candidate not in seen:
                seen.add(candidate)
                markers.append(candidate)
    return markers


def detect_sample_text_leak_from_transcript(transcript: str, markers: list[str], *, min_hits: int = 2) -> dict[str, Any] | None:
    normalized = normalize_text_for_leak_detection(transcript)
    if not normalized:
        return None
    matched = [marker for marker in markers if marker in normalized]
    if len(matched) < max(1, int(min_hits)):
        return None
    return {
        "text_leak": True,
        "matched_markers": matched[:8],
        "matched_marker_count": len(matched),
        "transcript": transcript[:500],
    }


def normalize_text_for_leak_detection(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").upper()
    kept: list[str] = []
    for char in normalized:
        if ("\u4e00" <= char <= "\u9fff") or (char.isascii() and char.isalnum()):
            kept.append(char)
    return "".join(kept)


def load_voice_reference_profile(voice_sample: Path, sf_module: object, sample_rate: int, signature_seconds: float) -> dict[str, Any] | None:
    import numpy as np

    raw, source_rate = sf_module.read(str(voice_sample), dtype="float32")
    reference = _resample_linear(_mono_float32(raw), int(source_rate), sample_rate)
    if len(reference) < sample_rate:
        return None
    active_start, active_end = _active_audio_bounds(reference, sample_rate)
    active = reference[active_start:active_end]
    signature_len = min(len(active), max(int(sample_rate * 1.5), int(sample_rate * signature_seconds)))
    if signature_len >= len(active):
        signature_offset = active_start
    else:
        signature_offset = active_start + (len(active) - signature_len) // 2
    signature = reference[signature_offset : signature_offset + signature_len]
    signature = signature - float(np.mean(signature))
    if float(np.sqrt(np.sum(signature * signature))) <= 1e-6:
        return None
    return {
        "reference_len": int(len(reference)),
        "signature": signature.astype(np.float32),
        "signature_offset": int(signature_offset),
        "sample_rate": sample_rate,
    }


def detect_voice_sample_leak(audio: object, profile: dict[str, Any], threshold: float, edge_seconds: float) -> dict[str, Any] | None:
    import numpy as np

    sample_rate = int(profile["sample_rate"])
    audio_arr = np.asarray(audio, dtype=np.float32)
    score, signature_pos = best_normalized_correlation(audio_arr, profile["signature"])
    if score < threshold:
        return None
    reference_len = int(profile["reference_len"])
    signature_offset = int(profile["signature_offset"])
    leak_start = signature_pos - signature_offset
    leak_end = leak_start + reference_len
    clamped_start = max(0, leak_start)
    clamped_end = min(len(audio_arr), leak_end)
    edge_samples = int(edge_seconds * sample_rate)
    start_distance = clamped_start
    end_distance = len(audio_arr) - clamped_end
    if start_distance <= edge_samples and end_distance <= edge_samples:
        position = "start" if start_distance <= end_distance else "end"
    elif start_distance <= edge_samples:
        position = "start"
    elif end_distance <= edge_samples:
        position = "end"
    else:
        position = "middle"
    return {
        "score": round(score, 6),
        "signature_pos": int(signature_pos),
        "leak_start": int(leak_start),
        "leak_end": int(leak_end),
        "clamped_start": int(clamped_start),
        "clamped_end": int(clamped_end),
        "start_distance": int(start_distance),
        "end_distance": int(end_distance),
        "position": position,
    }


def best_normalized_correlation(signal: object, template: object) -> tuple[float, int]:
    import numpy as np

    signal_arr = np.asarray(signal, dtype=np.float64)
    template_arr = np.asarray(template, dtype=np.float64)
    count = len(signal_arr)
    width = len(template_arr)
    if count < width or width <= 0:
        return 0.0, 0
    template_arr = template_arr - float(template_arr.mean())
    template_norm = float(np.sqrt(np.sum(template_arr * template_arr)))
    if template_norm <= 1e-9:
        return 0.0, 0
    fft_size = 1 << (max(1, count + width - 1) - 1).bit_length()
    corr_full = np.fft.irfft(
        np.fft.rfft(signal_arr, fft_size) * np.fft.rfft(template_arr[::-1], fft_size),
        fft_size,
    )
    corr = corr_full[width - 1 : count]
    cumsum = np.concatenate(([0.0], np.cumsum(signal_arr)))
    cumsum2 = np.concatenate(([0.0], np.cumsum(signal_arr * signal_arr)))
    sums = cumsum[width:] - cumsum[:-width]
    sums2 = cumsum2[width:] - cumsum2[:-width]
    variance = np.maximum(sums2 - (sums * sums / width), 1e-12)
    scores = corr / (template_norm * np.sqrt(variance))
    index = int(np.nanargmax(scores))
    return float(scores[index]), index


def _mono_float32(data: object):
    import numpy as np

    audio = np.asarray(data, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    return audio


def _resample_linear(audio: object, source_rate: int, target_rate: int):
    import numpy as np

    audio = np.asarray(audio, dtype=np.float32)
    if source_rate == target_rate or len(audio) == 0:
        return audio
    new_len = max(1, int(round(len(audio) * target_rate / source_rate)))
    old_positions = np.arange(len(audio), dtype=np.float32)
    new_positions = np.arange(new_len, dtype=np.float32) * source_rate / target_rate
    return np.interp(new_positions, old_positions, audio).astype(np.float32)


def _active_audio_bounds(audio: object, sample_rate: int) -> tuple[int, int]:
    import numpy as np

    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) == 0:
        return 0, 0
    frame = max(1, int(sample_rate * 0.025))
    if len(audio) <= frame:
        return 0, len(audio)
    frames = []
    for start in range(0, len(audio) - frame + 1, frame):
        window = audio[start : start + frame]
        frames.append(float(np.sqrt(np.mean(window * window))))
    rms = np.asarray(frames, dtype=np.float32)
    if not len(rms) or float(rms.max()) <= 1e-6:
        return 0, len(audio)
    threshold = max(0.0025, float(rms.max()) * 0.06)
    active = np.flatnonzero(rms >= threshold)
    if not len(active):
        return 0, len(audio)
    pad = int(sample_rate * 0.08)
    start = max(0, int(active[0]) * frame - pad)
    end = min(len(audio), (int(active[-1]) + 1) * frame + pad)
    return start, end
