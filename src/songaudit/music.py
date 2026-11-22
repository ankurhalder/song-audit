"""Tempo, key, tuning and structural segmentation."""

from __future__ import annotations

import numpy as np
import librosa

from .util import clamp, db_pow, frame_energies, percentile

NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Krumhansl-Kessler key profiles.
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def estimate_tempo(y: np.ndarray, sr: int) -> dict:
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
    tempo, beats = librosa.beat.beat_track(
        onset_envelope=onset_env, sr=sr, hop_length=512, units="time"
    )
    tempo = float(np.atleast_1d(tempo)[0])
    if not np.isfinite(tempo) or tempo <= 0:
        tempo = 0.0

    confidence = 0.0
    if tempo > 0 and onset_env.size > 10:
        autocorr = librosa.autocorrelate(onset_env, max_size=min(onset_env.size // 2, 4000))
        lag = int(round((60.0 / tempo) * sr / 512))
        if 0 < lag < autocorr.size:
            confidence = clamp(float(autocorr[lag] / max(1e-9, autocorr[0])) / 0.35, 0.0, 1.0)

    return {"bpm": round(tempo, 1), "tempo_confidence": round(confidence, 3),
            "beat_count": int(len(beats))}


def estimate_key(chroma_mean: np.ndarray) -> dict:
    chroma_mean = np.asarray(chroma_mean, dtype=np.float64)
    chroma_mean = chroma_mean - chroma_mean.mean()
    scores = []
    for mode, profile in (("major", MAJOR_PROFILE), ("minor", MINOR_PROFILE)):
        for root in range(12):
            rotated = np.roll(profile - profile.mean(), root)
            denom = np.linalg.norm(chroma_mean) * np.linalg.norm(rotated)
            corr = float(np.dot(chroma_mean, rotated) / denom) if denom else 0.0
            scores.append((corr, root, mode))
    scores.sort(key=lambda item: item[0], reverse=True)
    best_corr, root, mode = scores[0]
    second = scores[1][0]
    margin = best_corr - second
    confidence = clamp(0.45 + margin * 5.0, 0.0, 1.0)
    return {"key": f"{NOTES[root]} {mode}", "key_confidence": round(confidence, 3),
            "key_correlation": round(best_corr, 3)}


def segment_sections(y: np.ndarray, sr: int, max_sections: int = 8) -> list:
    duration = len(y) / sr
    hop = 1024
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    frames = chroma.shape[1]

    if duration < 20 or frames < 40:
        energy = frame_energies(y, max(1, int(0.05 * sr)), max(1, int(0.025 * sr)))
        return [{
            "index": 1, "label": "Full track", "start_s": 0.0,
            "end_s": round(duration, 2), "duration_s": round(duration, 2),
            "rms_db": round(float(percentile(db_pow(energy), 50)), 2),
        }]

    k = int(clamp(round(duration / 22), 3, max_sections))
    k = min(k, max(2, frames // 8))
    boundaries = np.asarray(librosa.segment.agglomerative(chroma, k), dtype=int)
    edges = np.unique(np.clip(np.concatenate(([0], boundaries, [frames])), 0, frames))

    sections = []
    for index in range(len(edges) - 1):
        start_frame, end_frame = int(edges[index]), int(edges[index + 1])
        start = float(librosa.frames_to_time(start_frame, sr=sr, hop_length=hop))
        end = float(librosa.frames_to_time(end_frame, sr=sr, hop_length=hop))
        if end - start < 1.0:
            continue
        chunk = y[int(start * sr):int(end * sr)]
        level = float(db_pow(np.mean(chunk.astype(np.float64) ** 2))) if chunk.size else -120.0
        sections.append({
            "index": len(sections) + 1,
            "start_s": round(start, 2),
            "end_s": round(min(end, duration), 2),
            "duration_s": round(min(end, duration) - start, 2),
            "rms_db": round(level, 2),
        })

    if not sections:
        level = float(db_pow(np.mean(np.asarray(y, dtype=np.float64) ** 2))) if y.size else -120.0
        return [{
            "index": 1, "label": "Full track", "start_s": 0.0,
            "end_s": round(duration, 2), "duration_s": round(duration, 2),
            "rms_db": round(level, 2),
        }]

    ranked = sorted(range(len(sections)), key=lambda i: sections[i]["rms_db"], reverse=True)
    for rank, position in enumerate(ranked):
        sections[position]["label"] = "Section %d" % sections[position]["index"]
        if rank == 0 and len(sections) > 2:
            sections[position]["label"] += " (peak energy)"
        elif rank == len(ranked) - 1 and len(sections) > 3:
            sections[position]["label"] += " (lowest energy)"
    return sections


def analyze_music(y: np.ndarray, sr: int) -> dict:
    tempo = estimate_tempo(y, sr)
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=2048)
    key = estimate_key(chroma.mean(axis=1))
    tuning_cents = float(librosa.estimate_tuning(y=y, sr=sr)) * 100.0
    sections = segment_sections(y, sr)

    rms_all = float(np.sqrt(np.mean(np.asarray(y, dtype=np.float64) ** 2))) if y.size else 0.0
    tail = y[-int(0.1 * sr):] if y.size > int(0.1 * sr) else y
    tail_rms = float(np.sqrt(np.mean(np.asarray(tail, dtype=np.float64) ** 2))) if tail.size else 0.0
    hard_ending = bool(rms_all > 1e-4 and tail_rms > rms_all * 0.5)

    return {
        **tempo,
        **key,
        "tuning_cents": round(tuning_cents, 1),
        "sections": sections,
        "section_count": len(sections),
        "hard_ending": hard_ending,
    }
