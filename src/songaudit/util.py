"""Small numeric helpers shared across the analysis modules."""

from __future__ import annotations

import math

import numpy as np

FLOOR_DB = -120.0


def db(x, floor: float = FLOOR_DB):
    """Convert linear amplitude (or an array of them) to dBFS."""
    arr = np.asarray(x, dtype=np.float64)
    eps = 10.0 ** (floor / 20.0)
    return 20.0 * np.log10(np.maximum(np.abs(arr), eps))


def db_pow(x, floor: float = FLOOR_DB):
    """Convert a power quantity to dB."""
    arr = np.asarray(x, dtype=np.float64)
    eps = 10.0 ** (floor / 10.0)
    return 10.0 * np.log10(np.maximum(arr, eps))


def as_float(value, default: float = 0.0) -> float:
    """Return a finite float, or a default when the value is NaN/inf."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def rms(x) -> float:
    arr = np.asarray(x, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr * arr)))


def frame_energies(x, frame: int, hop: int) -> np.ndarray:
    """Mean energy per frame using an O(n) cumulative-sum pass."""
    arr = np.asarray(x, dtype=np.float64)
    if arr.size < frame:
        pad = np.zeros(frame - arr.size, dtype=np.float64)
        arr = np.concatenate([arr, pad])
    cumulative = np.concatenate([[0.0], np.cumsum(arr * arr)])
    starts = np.arange(0, arr.size - frame + 1, hop)
    energies = (cumulative[starts + frame] - cumulative[starts]) / frame
    return np.maximum(energies, 1e-20)


def frame_rms_db(x, frame: int, hop: int, floor: float = FLOOR_DB) -> np.ndarray:
    return db_pow(frame_energies(x, frame, hop), floor=floor)


def percentile(values, q: float, default: float = 0.0) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return default
    return float(np.percentile(arr, q))


def clamp(value: float, low: float, high: float) -> float:
    return float(max(low, min(high, value)))


def linear_score(value: float, best: float, worst: float) -> float:
    """Map a metric onto 0..100 where *best* scores 100 and *worst* scores 0."""
    if best == worst:
        return 100.0
    return clamp(100.0 * (value - worst) / (best - worst), 0.0, 100.0)
