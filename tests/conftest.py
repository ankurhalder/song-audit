from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

SR = 44100


def _make_track(duration: float = 12.0, sr: int = SR) -> np.ndarray:
    bpm = 120.0
    beat = 60.0 / bpm
    total = int(duration * sr)
    t = np.arange(total) / sr
    mix = np.zeros(total, dtype=np.float64)
    rng = np.random.default_rng(7)

    chords = [
        [261.63, 329.63, 392.00],
        [220.00, 261.63, 329.63],
        [174.61, 220.00, 261.63],
        [196.00, 246.94, 293.66],
    ]
    bars = int(np.ceil(duration / (4 * beat)))
    for bar in range(bars):
        start = bar * 4 * beat
        if start >= duration:
            break
        stop = min(duration, start + 4 * beat)
        segment = slice(int(start * sr), int(stop * sr))
        for freq in chords[bar % 4]:
            mix[segment] += 0.07 * np.sin(2 * np.pi * freq * t[segment])

    kick_times = np.arange(0, duration, beat)
    for index, start in enumerate(kick_times):
        stop = min(duration, start + 0.18)
        segment = slice(int(start * sr), int(stop * sr))
        local = np.arange(segment.stop - segment.start) / sr
        mix[segment] += 0.55 * np.exp(-16 * local) * np.sin(2 * np.pi * 55 * local)

    hat_times = np.arange(0, duration, beat / 2)
    for index, start in enumerate(hat_times):
        stop = min(duration, start + 0.03)
        segment = slice(int(start * sr), int(stop * sr))
        length = segment.stop - segment.start
        noise = rng.standard_normal(length) * np.exp(-70 * np.arange(length) / sr)
        mix[segment] += 0.05 * noise

    fade = int(0.2 * sr)
    mix[-fade:] *= np.linspace(1.0, 0.0, fade)
    mix = 0.8 * mix / max(1e-9, np.max(np.abs(mix)))
    return mix


@pytest.fixture(scope="session")
def demo_wav(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("audio") / "demo.wav"
    mono = _make_track()
    stereo = np.stack([mono, np.roll(mono, 32) * 0.98], axis=1).astype(np.float32)
    sf.write(str(path), stereo, SR, subtype="PCM_16")
    return str(path)


@pytest.fixture(scope="session")
def click_wav(tmp_path_factory) -> str:
    sr = SR
    duration = 10.0
    beat = 0.5
    total = int(duration * sr)
    signal = np.zeros(total, dtype=np.float32)
    for start in np.arange(0, duration, beat):
        segment = slice(int(start * sr), int((start + 0.05) * sr))
        length = segment.stop - segment.start
        signal[segment] += (0.9 * np.exp(-40 * np.arange(length) / sr)).astype(np.float32)

    path = tmp_path_factory.mktemp("audio") / "click.wav"
    sf.write(str(path), np.stack([signal, signal], axis=1), sr, subtype="PCM_16")
    return str(path)


@pytest.fixture(scope="session")
def clipped_wav(tmp_path_factory) -> str:
    sr = SR
    t = np.arange(int(3 * sr)) / sr
    tone = np.clip(1.6 * np.sin(2 * np.pi * 440 * t), -1.0, 1.0)
    path = tmp_path_factory.mktemp("audio") / "clipped.wav"
    sf.write(str(path), np.stack([tone, tone], axis=1), sr, subtype="PCM_16")
    return str(path)
