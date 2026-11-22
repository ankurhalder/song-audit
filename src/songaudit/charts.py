"""Matplotlib figures rendered to base64 PNGs for the HTML report."""

from __future__ import annotations

import base64
import io

import librosa
import librosa.display
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

BACKGROUND = "#0b0d12"
PANEL = "#111420"
GRID = "#252a36"
TEXT = "#d7dbe6"
MUTED = "#7d8496"
ACCENT = "#8b5cf6"
TEAL = "#22d3ee"
AMBER = "#f59e0b"
RED = "#ef4444"
GREEN = "#34d399"


def _apply_theme() -> None:
    plt.rcParams.update({
        "figure.facecolor": BACKGROUND,
        "axes.facecolor": PANEL,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "text.color": TEXT,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": GRID,
        "font.size": 8,
    })


def _style(ax) -> None:
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_color(GRID)
    ax.tick_params(colors=MUTED, labelsize=7)
    ax.grid(color=GRID, linewidth=0.5, alpha=0.5)


def _encode(fig) -> str:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=140, bbox_inches="tight", facecolor=BACKGROUND)
    plt.close(fig)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _envelope(mono: np.ndarray, sr: int, buckets: int = 1600):
    mono = np.asarray(mono, dtype=np.float32)
    n = mono.size
    if n == 0:
        return np.array([0.0]), np.array([0.0]), np.array([0.0])
    buckets = min(buckets, max(1, n))
    edges = np.linspace(0, n, buckets + 1).astype(int)
    lows = np.array([mono[a:b].min() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
    highs = np.array([mono[a:b].max() if b > a else 0.0 for a, b in zip(edges[:-1], edges[1:])])
    times = edges[:-1] / sr
    return times, lows, highs


def waveform_chart(report: dict, mono: np.ndarray, sr: int) -> str:
    _apply_theme()
    duration = len(mono) / sr
    times, lows, highs = _envelope(mono, sr)

    fig, (top, bottom) = plt.subplots(
        2, 1, figsize=(10.5, 4.6), sharex=True,
        gridspec_kw={"height_ratios": [1.5, 1.0], "hspace": 0.12},
    )
    fig.patch.set_facecolor(BACKGROUND)

    top.fill_between(times, lows, highs, color=ACCENT, linewidth=0, alpha=0.85)
    top.set_xlim(0, duration)
    top.set_ylim(-1.05, 1.05)
    top.set_ylabel("amplitude")
    _style(top)

    for section in report["music"]["sections"]:
        top.axvline(section["start_s"], color=TEAL, linewidth=0.7, alpha=0.55)
        if section["duration_s"] > duration * 0.04:
            top.text(
                section["start_s"] + max(0.4, duration * 0.004), 0.9,
                "S" + str(section["index"]), color=TEAL, fontsize=6.5,
                va="top", ha="left", alpha=0.9,
            )

    timeline = report["mastering"]["loudness_timeline"]
    if timeline["times"]:
        bottom.plot(timeline["times"], timeline["lufs"], color=TEAL, linewidth=1.2)
        bottom.axhline(-14, color=AMBER, linestyle="--", linewidth=0.8, alpha=0.8)
        bottom.fill_between(
            timeline["times"], timeline["lufs"], -30,
            color=TEAL, alpha=0.08, linewidth=0,
        )
        lo = min(timeline["lufs"]) - 2
        hi = max(timeline["lufs"]) + 2
        bottom.set_ylim(min(lo, -22), max(hi, -8))
    bottom.set_ylabel("LUFS (3 s)")
    bottom.set_xlabel("seconds")
    _style(bottom)

    return _encode(fig)


def spectrum_chart(report: dict) -> str:
    _apply_theme()
    bands = report["spectral"]["bands"]
    labels = [b["name"].replace("_", " ") for b in bands]
    values = [b["rel_db"] for b in bands]
    deviations = report["spectral"]["deviations_db"]

    fig, ax = plt.subplots(figsize=(10.5, 2.9))
    fig.patch.set_facecolor(BACKGROUND)
    colors = [AMBER if abs(deviations.get(b["name"], 0)) > 5 else ACCENT for b in bands]
    bars = ax.bar(range(len(bands)), values, color=colors, width=0.62, alpha=0.9)
    ax.set_xticks(range(len(bands)))
    ax.set_xticklabels([
        b["name"].replace("_", " ") + "\n" + str(b["lo_hz"]) + "-" + str(b["hi_hz"]) + " Hz"
        for b in bands
    ], fontsize=6.5)
    ax.set_ylabel("dB relative to total")
    ax.set_title("Long-term spectral balance (amber = more than 5 dB from the track tilt)", fontsize=8.5)
    _style(ax)

    return _encode(fig)


def spectrogram_chart(report: dict, mono: np.ndarray, sr: int) -> str:
    _apply_theme()
    fig, ax = plt.subplots(figsize=(10.5, 3.0))
    fig.patch.set_facecolor(BACKGROUND)
    stft = librosa.stft(np.asarray(mono, dtype=np.float32), n_fft=2048, hop_length=1024)
    db = librosa.amplitude_to_db(np.abs(stft), ref=np.max)
    image = librosa.display.specshow(
        db, sr=sr, hop_length=1024, x_axis="time", y_axis="log",
        cmap="magma", ax=ax, vmin=-80, vmax=0,
    )
    ax.set_title("Spectrogram", fontsize=8.5)
    ax.set_xlabel("seconds")
    ax.set_ylabel("Hz")
    _style(ax)
    ax.grid(False)
    colorbar = fig.colorbar(image, ax=ax, format="%+2.0f dB", pad=0.01)
    colorbar.ax.tick_params(colors=MUTED, labelsize=6)
    colorbar.outline.set_edgecolor(GRID)
    return _encode(fig)


def radar_chart(report: dict) -> str:
    _apply_theme()
    categories = report["score"]["categories"]
    labels = [c["label"].replace(" & ", " &\n") for c in categories]
    values = [c["score"] for c in categories]

    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    values = values + values[:1]
    angles = angles + angles[:1]

    fig = plt.figure(figsize=(3.9, 3.9))
    fig.patch.set_facecolor(BACKGROUND)
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor(PANEL)
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], color=MUTED, fontsize=6)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, color=TEXT, fontsize=6.5)
    ax.grid(color=GRID, linewidth=0.6)
    ax.spines["polar"].set_color(GRID)

    ax.plot(angles, values, color=ACCENT, linewidth=1.6)
    ax.fill(angles, values, color=ACCENT, alpha=0.25)
    ax.scatter(angles[:-1], values[:-1], color=TEAL, s=14, zorder=5)
    return _encode(fig)


def build_charts(report: dict, mono: np.ndarray, sr: int) -> dict:
    charts = {
        "radar": radar_chart(report),
        "spectrum": spectrum_chart(report),
    }
    try:
        charts["waveform"] = waveform_chart(report, mono, sr)
    except Exception:
        charts["waveform"] = None
    try:
        charts["spectrogram"] = spectrogram_chart(report, mono, sr)
    except Exception:
        charts["spectrogram"] = None
    return charts
