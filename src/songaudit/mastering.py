"""Objective mastering measurements: loudness, peaks, clipping, stereo field."""

from __future__ import annotations

import numpy as np
import pyloudnorm as pyln
from scipy.signal import resample_poly

from .util import db, db_pow, frame_energies, percentile, rms


def integrated_loudness(mono: np.ndarray, sr: int) -> float:
    """ITU-R BS.1770-4 integrated loudness in LUFS (pyloudnorm implementation)."""
    meter = pyln.Meter(sr)
    value = meter.integrated_loudness(np.asarray(mono, dtype=np.float64))
    return float(value) if np.isfinite(value) else -70.0


def loudness_timeline(mono: np.ndarray, sr: int, window: float = 3.0, hop: float = 0.5,
                      max_windows: int = 600) -> dict:
    """Short-term loudness (3 s window), sampled on a fixed grid."""
    total = mono.size
    win = int(window * sr)
    if total < win:
        value = integrated_loudness(mono, sr)
        return {"times": [total / sr / 2], "lufs": [value]}

    step = int(hop * sr)
    starts = np.arange(0, total - win + 1, step)
    if starts.size > max_windows:
        keep = np.linspace(0, starts.size - 1, max_windows).astype(int)
        starts = starts[keep]

    meter = pyln.Meter(sr)
    values = []
    for start in starts:
        seg = np.asarray(mono[start:start + win], dtype=np.float64)
        value = meter.integrated_loudness(seg)
        values.append(float(value) if np.isfinite(value) else -70.0)

    times = (starts + win / 2) / sr
    return {"times": [round(float(t), 3) for t in times], "lufs": [round(v, 2) for v in values]}


def true_peak_db(data: np.ndarray, sr: int, oversample: int = 4) -> float:
    """Inter-sample peak using polyphase oversampling, chunked to bound memory."""
    peak = 0.0
    chunk = int(60 * sr)
    guard = 128

    for channel in range(data.shape[1]):
        x = np.asarray(data[:, channel], dtype=np.float64)
        for start in range(0, x.size, chunk):
            seg = x[start:start + chunk]
            if seg.size == 0:
                continue
            up = resample_poly(seg, oversample, 1)
            if start > 0:
                up = up[guard:]
            if start + chunk < x.size:
                up = up[:-guard]
            if up.size:
                peak = max(peak, float(np.max(np.abs(up))))

    return float(db(peak))


def _longest_run(mask: np.ndarray) -> int:
    if not bool(mask.any()):
        return 0
    padded = np.concatenate(([False], mask.astype(bool), [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    if edges.size < 2:
        return 0
    return int((edges[1::2] - edges[0::2]).max())


def analyze_mastering(data: np.ndarray, sr: int) -> dict:
    mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
    duration = data.shape[0] / sr

    lufs = integrated_loudness(mono, sr)
    timeline = loudness_timeline(mono, sr)

    lra = percentile(timeline["lufs"], 95) - percentile(timeline["lufs"], 10)
    loudest = max(timeline["lufs"]) if timeline["lufs"] else lufs

    sample_peak = float(np.max(np.abs(data))) if data.size else 0.0
    tp_db = true_peak_db(data, sr)

    threshold = 0.999
    clipped = np.abs(data) >= threshold
    clipped_count = int(clipped.sum())
    clipped_ratio = clipped_count / max(1, data.size)
    longest = max((_longest_run(clipped[:, c]) for c in range(clipped.shape[1])), default=0)

    dc = [float(data[:, c].mean()) for c in range(data.shape[1])]

    frame = max(1, int(0.05 * sr))
    energies = frame_energies(mono, frame, max(1, frame // 2))
    frame_db = db_pow(energies)
    quiet = percentile(frame_db, 1)
    active = frame_db[frame_db > -70.0]
    dynamic_range = (percentile(active, 95) - percentile(active, 10)) if active.size else 0.0

    silent = np.abs(mono) <= 1e-3
    above = np.flatnonzero(~silent)
    if above.size:
        head_silence = float(above[0] / sr)
        tail_silence = float((mono.size - 1 - above[-1]) / sr)
    else:
        head_silence = duration
        tail_silence = duration

    return {
        "integrated_lufs": round(lufs, 2),
        "loudest_short_term_lufs": round(loudest, 2),
        "loudness_range_lu": round(float(lra), 2),
        "loudness_timeline": timeline,
        "sample_peak_db": round(float(db(sample_peak)), 2),
        "true_peak_db": round(tp_db, 2),
        "crest_factor_db": round(float(db(rms(mono)) - db(sample_peak)) * -1, 2),
        "clipping": {
            "count": clipped_count,
            "percent": round(100.0 * clipped_ratio, 5),
            "longest_run": longest,
        },
        "dc_offset": [round(v, 6) for v in dc],
        "quiet_passage_db": round(quiet, 2),
        "dynamic_range_db": round(float(dynamic_range), 2),
        "head_silence_s": round(head_silence, 3),
        "tail_silence_s": round(tail_silence, 3),
        "duration_s": round(duration, 3),
    }


def analyze_stereo(data: np.ndarray) -> dict:
    if data.shape[1] < 2:
        return {
            "channels": 1, "correlation": 1.0, "width_percent": 0.0,
            "side_mid_db": -120.0, "mono_loss_db": 0.0, "balance_db": 0.0,
        }

    left = np.asarray(data[:, 0], dtype=np.float64)
    right = np.asarray(data[:, 1], dtype=np.float64)
    step = max(1, left.size // 200_000)
    sample = slice(None, None, step)

    if np.std(left[sample]) < 1e-9 or np.std(right[sample]) < 1e-9:
        corr = 0.0 if (np.std(left[sample]) < 1e-9 and np.std(right[sample]) < 1e-9) else 1.0
    else:
        corr = float(np.corrcoef(left[sample], right[sample])[0, 1])
        corr = corr if np.isfinite(corr) else 0.0

    mid = 0.5 * (left + right)
    side = 0.5 * (left - right)
    mid_rms, side_rms = rms(mid), rms(side)
    width = 100.0 * side_rms / max(1e-12, side_rms + mid_rms)
    mono_loss = float(db(rms(mid)) - db(max(rms(left), rms(right))))

    return {
        "channels": 2,
        "correlation": round(corr, 3),
        "width_percent": round(width, 1),
        "side_mid_db": round(float(db(side_rms) - db(mid_rms)), 2),
        "mono_loss_db": round(mono_loss, 2),
        "balance_db": round(float(db(rms(left)) - db(rms(right))), 2),
    }
