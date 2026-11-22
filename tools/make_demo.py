"""Generate a royalty-free demo track so anyone can try SongAudit in seconds."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
BPM = 120.0
BEAT = 60.0 / BPM
BAR = 4 * BEAT

CHORDS = {
    "C": [261.63, 329.63, 392.00],
    "Am": [220.00, 261.63, 329.63],
    "F": [174.61, 220.00, 261.63],
    "G": [196.00, 246.94, 293.66],
}
ROOTS = {"C": 65.41, "Am": 55.00, "F": 43.65, "G": 49.00}
PROGRESSION = ["C", "Am", "F", "G"]

# (name, bars, intensity)
ARRANGEMENT = [
    ("intro", 2, 0.35),
    ("verse", 4, 0.70),
    ("chorus", 4, 1.00),
    ("outro", 2, 0.40),
]


def build() -> np.ndarray:
    total_bars = sum(bars for _, bars, _ in ARRANGEMENT)
    duration = total_bars * BAR
    total = int(duration * SR)
    t = np.arange(total) / SR
    left = np.zeros(total)
    right = np.zeros(total)
    rng = np.random.default_rng(11)

    cursor = 0.0
    for name, bars, intensity in ARRANGEMENT:
        for bar in range(bars):
            start = cursor + bar * BAR
            stop = min(duration, start + BAR)
            index = slice(int(start * SR), int(stop * SR))
            chord = PROGRESSION[(int(start / BAR)) % 4]

            for freq in CHORDS[chord]:
                pad = 0.055 * intensity
                left[index] += pad * np.sin(2 * np.pi * freq * t[index])
                right[index] += pad * np.sin(2 * np.pi * freq * 1.003 * t[index])

            if intensity > 0.5:
                for hit in range(4):
                    kick_start = start + hit * BEAT
                    kick = slice(int(kick_start * SR), int(min(duration, kick_start + 0.2) * SR))
                    local = np.arange(kick.stop - kick.start) / SR
                    left[kick] += 0.55 * intensity * np.exp(-15 * local) * np.sin(2 * np.pi * 52 * local)
                    right[kick] += 0.55 * intensity * np.exp(-15 * local) * np.sin(2 * np.pi * 52 * local)

                for hit in range(8):
                    hat_start = start + hit * BEAT / 2
                    hat = slice(int(hat_start * SR), int(min(duration, hat_start + 0.04) * SR))
                    length = hat.stop - hat.start
                    noise = rng.standard_normal(length) * np.exp(-60 * np.arange(length) / SR)
                    left[hat] += 0.04 * intensity * noise
                    right[hat] += 0.04 * intensity * noise

                root = ROOTS[chord]
                bass = slice(int(start * SR), int(stop * SR))
                left[bass] += 0.10 * intensity * np.sin(2 * np.pi * root * t[bass])
                right[bass] += 0.10 * intensity * np.sin(2 * np.pi * root * t[bass])

            if name == "chorus":
                melody = CHORDS[chord][2] * 2
                lead = slice(int(start * SR), int(stop * SR))
                phase = 2 * np.pi * melody * t[lead]
                left[lead] += 0.05 * np.sin(phase) * (0.6 + 0.4 * np.sin(2 * np.pi * 2 * t[lead]))
                right[lead] += 0.05 * np.sin(phase + 0.4) * (0.6 + 0.4 * np.sin(2 * np.pi * 2 * t[lead]))

        cursor += bars * BAR

    fade_in = int(0.8 * SR)
    fade_out = int(2.0 * SR)
    left[:fade_in] *= np.linspace(0, 1, fade_in)
    right[:fade_in] *= np.linspace(0, 1, fade_in)
    left[-fade_out:] *= np.linspace(1, 0, fade_out)
    right[-fade_out:] *= np.linspace(1, 0, fade_out)

    stereo = np.stack([left, right], axis=1)

    # Master to roughly -14 LUFS with a soft-knee limiter so the demo looks like a release.
    import pyloudnorm

    meter = pyloudnorm.Meter(SR)
    loudness = meter.integrated_loudness(np.asarray(stereo, dtype=np.float64))
    if loudness < -1:
        stereo *= 10 ** ((-14.0 - loudness) / 20.0)

    peak = float(np.max(np.abs(stereo)))
    if peak > 0.89:
        stereo *= 0.89 / peak
    return stereo.astype(np.float32)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/demo.wav")
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), build(), SR, subtype="PCM_16")
    print("wrote " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
