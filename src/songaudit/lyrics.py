"""Optional lyric transcription and vocal statistics (faster-whisper)."""

from __future__ import annotations

import os
import re

import numpy as np

from .audio import resample

PROFANITY = {
    "fuck", "fucking", "shit", "bitch", "asshole", "damn", "cunt", "bastard", "dick",
}


def transcribe(mono: np.ndarray, sr: int, model_name: str | None = None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "Lyric analysis needs the optional extra: pip install 'songaudit[lyrics]'"
        ) from exc

    audio = resample(np.asarray(mono, dtype=np.float32), sr, 16000)
    model_name = model_name or os.environ.get("SONGAUDIT_WHISPER_MODEL", "base")
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio, vad_filter=True, beam_size=1)

    collected = []
    for segment in segments:
        text = (segment.text or "").strip()
        if text:
            collected.append({
                "start_s": round(float(segment.start), 2),
                "end_s": round(float(segment.end), 2),
                "text": text,
            })

    transcript = " ".join(item["text"] for item in collected).strip()
    duration = audio.size / 16000.0
    spoken = sum(item["end_s"] - item["start_s"] for item in collected)
    words = transcript.split()

    tokens = re.findall(r"[a-z']+", transcript.lower())
    grams = [" ".join(tokens[i:i + 4]) for i in range(max(0, len(tokens) - 3))]
    repetition = 1.0 - (len(set(grams)) / len(grams)) if grams else 0.0
    minutes = max(spoken, 1.0) / 60.0

    return {
        "model": model_name,
        "language": getattr(info, "language", None),
        "language_probability": round(float(getattr(info, "language_probability", 0.0)), 3),
        "transcript": transcript,
        "segments": collected,
        "word_count": len(words),
        "unique_word_count": len(set(w.lower() for w in words)),
        "words_per_minute": round(len(words) / minutes, 1),
        "vocal_coverage": round(min(1.0, spoken / max(duration, 1e-6)), 3),
        "repetition_ratio": round(repetition, 3),
        "profanity_count": sum(1 for w in tokens if w in PROFANITY),
    }
