"""Long-term spectral balance, brightness and codec-cutoff diagnostics."""

from __future__ import annotations

import numpy as np
import librosa

from .util import db_pow, rms

BANDS = (
    ("sub", 20, 60),
    ("bass", 60, 120),
    ("low_mid", 120, 500),
    ("mid", 500, 2000),
    ("high_mid", 2000, 6000),
    ("presence", 6000, 10000),
    ("air", 10000, 16000),
)

FIT_BANDS = {name for name, _, _ in BANDS}


def analyze_spectral(mono: np.ndarray, sr: int) -> dict:
    n_fft = 4096
    hop = 2048
    power = np.abs(librosa.stft(mono, n_fft=n_fft, hop_length=hop)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    psd = power.mean(axis=1)
    total = float(psd.sum()) + 1e-20

    bands = []
    for name, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        energy = float(psd[mask].sum())
        rel_db = 10.0 * np.log10(max(energy, 1e-20) / total)
        bands.append({
            "name": name,
            "lo_hz": lo,
            "hi_hz": hi,
            "rel_db": round(float(rel_db), 2),
        })

    # Tilt (dB per octave) plus per-band residual from that tilt.
    fit = [(b["name"], 10 * np.log10(max(1e-20, (b["lo_hz"] + b["hi_hz"]) / 2)), b["rel_db"])
           for b in bands if b["name"] in FIT_BANDS]
    x = np.array([f[1] for f in fit], dtype=np.float64)
    y = np.array([f[2] for f in fit], dtype=np.float64)
    slope, intercept = np.polyfit(x, y, 1) if x.size >= 2 else (0.0, 0.0)

    deviations = {}
    for name, octave_freq, level in fit:
        expected = slope * octave_freq + intercept
        deviations[name] = round(float(level - expected), 2)

    cumulative = np.cumsum(psd)
    rolloff_99 = float(freqs[min(len(freqs) - 1, int(np.searchsorted(cumulative, 0.99 * cumulative[-1])))])
    rolloff_999 = float(freqs[min(len(freqs) - 1, int(np.searchsorted(cumulative, 0.999 * cumulative[-1])))])
    rolloff_85 = float(np.mean(librosa.feature.spectral_rolloff(y=mono, sr=sr, roll_percent=0.85)))

    harmonic, percussive = librosa.effects.hpss(mono)
    h_rms, p_rms = rms(harmonic), rms(percussive)
    percussive_ratio = float(p_rms / max(1e-12, h_rms + p_rms))

    return {
        "bands": bands,
        "deviations_db": deviations,
        "tilt_db_per_octave": round(float(slope), 2),
        "centroid_hz": round(float(np.mean(librosa.feature.spectral_centroid(y=mono, sr=sr))), 1),
        "rolloff_85_hz": round(rolloff_85, 1),
        "rolloff_99_hz": round(rolloff_99, 1),
        "rolloff_999_hz": round(rolloff_999, 1),
        "flatness": round(float(np.mean(librosa.feature.spectral_flatness(y=mono))), 5),
        "high_frequency_cutoff_hz": round(rolloff_999, 1),
        "nyquist_hz": sr / 2,
        "harmonic_rms_db": round(float(db_pow(h_rms ** 2)), 2),
        "percussive_rms_db": round(float(db_pow(p_rms ** 2)), 2),
        "percussive_ratio": round(percussive_ratio, 3),
    }
