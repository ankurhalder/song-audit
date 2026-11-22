"""Record what the machine is playing - no microphone and no virtual cable needed.

Windows uses the WASAPI loopback of the default speaker, which is the native
equivalent of macOS BlackHole. On macOS you still need a loopback driver such as
BlackHole; on Linux the PulseAudio monitor source is used.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import soundfile as sf


def _loopback_devices():
    import soundcard as sc

    return [m for m in sc.all_microphones(include_loopback=True) if m.isloopback]


def pick_device(device: str | None = None):
    import soundcard as sc

    loopbacks = _loopback_devices()

    if device:
        for mic in loopbacks:
            if device.lower() in mic.name.lower():
                return mic
        names = ", ".join(m.name for m in loopbacks) or "(none)"
        raise SystemExit("No loopback device matched '" + device + "'. Available: " + names)

    if sys.platform == "win32":
        speaker = sc.default_speaker()
        return sc.get_microphone(id=str(speaker.name), include_loopback=True)

    if sys.platform.startswith("linux"):
        monitors = [m for m in sc.all_microphones(include_loopback=True) if "monitor" in m.name.lower()]
        if monitors:
            return monitors[0]
        raise SystemExit("No PulseAudio monitor source found. Install pulseaudio-utils or use --device.")

    for mic in loopbacks:
        if "blackhole" in mic.name.lower():
            return mic
    raise SystemExit(
        "macOS needs a loopback driver. Install BlackHole (https://existential.audio/blackhole/), "
        "then rerun; it does not exist for Windows, where this command works out of the box."
    )


def capture(output: str, seconds: float | None = None, device: str | None = None,
            samplerate: int = 48000, silence_stop: float = 4.0, min_seconds: float = 8.0) -> str:
    import soundcard as sc

    mic = pick_device(device)
    block = 0.1
    frames = int(samplerate * block)

    print("Capturing from: " + mic.name, file=sys.stderr)
    print("Play the track now. Recording stops on silence, Ctrl+C, or the time limit.", file=sys.stderr)

    started = time.time()
    silence = 0.0
    total = 0.0
    heard = 0.0
    loud = False

    with mic.recorder(samplerate=samplerate, channels=2) as recorder:
        with sf.SoundFile(output, "w", samplerate=samplerate, channels=2, subtype="PCM_16") as handle:
            while True:
                chunk = recorder.record(numframes=frames)
                chunk = np.asarray(chunk, dtype=np.float32)
                handle.write(chunk)
                total += block

                level = float(np.sqrt(np.mean(chunk ** 2))) if chunk.size else 0.0
                if level > 1e-4:
                    heard += block
                    if heard >= 2.0:
                        loud = True
                    if loud:
                        silence = 0.0
                elif loud:
                    silence += block

                elapsed = time.time() - started
                bars = int(min(1.0, level * 8) * 18)
                print(
                    "\r%6.1f s  [%s%s]  %.4f" % (total, "#" * bars, "." * (18 - bars), level),
                    end="", file=sys.stderr, flush=True,
                )

                if seconds and total >= seconds:
                    break
                if loud and total > max(min_seconds, 15.0) and silence >= silence_stop:
                    break
                if elapsed > (seconds or 900):
                    break

    print("", file=sys.stderr)
    return output
