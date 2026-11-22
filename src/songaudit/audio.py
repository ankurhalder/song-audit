"""Decoding helpers: everything downstream works on a stereo float32 array."""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .config import TARGET_SR


@dataclass
class AudioData:
    samples: np.ndarray  # shape (n, 2), float32
    sample_rate: int
    source_sample_rate: int
    subtype: str
    format: str
    frames: int


def _to_stereo(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    elif data.shape[1] > 2:
        data = data[:, :2]
    return np.ascontiguousarray(data, dtype=np.float32)


def load_audio(path: str, target_sr: int = TARGET_SR) -> AudioData:
    """Decode any libsndfile-supported file to stereo float32 at target_sr."""
    info = sf.info(str(path))
    data, sr = sf.read(str(path), always_2d=True, dtype="float32", frames=-1)
    data = _to_stereo(data)

    if sr != target_sr:
        factor = gcd(int(sr), int(target_sr))
        data = resample_poly(data, target_sr // factor, sr // factor, axis=0)
        data = np.ascontiguousarray(data, dtype=np.float32)

    return AudioData(
        samples=data,
        sample_rate=target_sr,
        source_sample_rate=int(info.samplerate),
        subtype=info.subtype or "unknown",
        format=info.format or "unknown",
        frames=int(data.shape[0]),
    )


def to_mono(data: np.ndarray) -> np.ndarray:
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 2 and arr.shape[1] > 1:
        return arr.mean(axis=1).astype(np.float32)
    if arr.ndim == 2:
        return arr[:, 0]
    return arr


def resample(y: np.ndarray, sr: int, target_sr: int) -> np.ndarray:
    if sr == target_sr:
        return np.asarray(y, dtype=np.float32)
    factor = gcd(int(sr), int(target_sr))
    out = resample_poly(np.asarray(y, dtype=np.float32), target_sr // factor, sr // factor)
    return np.ascontiguousarray(out, dtype=np.float32)
