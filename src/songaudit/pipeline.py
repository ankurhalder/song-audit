"""Orchestrates decoding, every analyzer, scoring and report assembly."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import __version__
from .audio import load_audio, resample, to_mono
from .config import ANALYSIS_SR
from .ingest import read_tags, sha256_file
from .mastering import analyze_mastering, analyze_stereo
from .music import analyze_music
from .score import score_report
from .spectral import analyze_spectral


def audit_file(path: str | Path, source_kind: str = "file",
               source_label: str | None = None, do_lyrics: bool = False) -> dict:
    path = Path(path)
    audio = load_audio(str(path))
    samples, sr = audio.samples, audio.sample_rate
    mono = to_mono(samples)

    mastering = analyze_mastering(samples, sr)
    stereo = analyze_stereo(samples)
    spectral = analyze_spectral(mono, sr)
    music = analyze_music(resample(mono, sr, ANALYSIS_SR), ANALYSIS_SR)

    lyrics = None
    if do_lyrics:
        from .lyrics import transcribe

        lyrics = transcribe(mono, sr)

    stat = path.stat()
    report = {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "tool": {"name": "songaudit", "version": __version__},
        "source": {
            "kind": source_kind,
            "label": source_label or path.name,
            "filename": path.name,
            "bytes": stat.st_size,
            "sha256": sha256_file(path),
        },
        "file": {
            "format": audio.format,
            "subtype": audio.subtype,
            "source_sample_rate": audio.source_sample_rate,
            "sample_rate": sr,
            "channels": int(samples.shape[1]),
            "duration_s": mastering["duration_s"],
        },
        "tags": read_tags(path),
        "mastering": mastering,
        "stereo": stereo,
        "spectral": spectral,
        "music": music,
        "lyrics": lyrics,
        "analysis": {
            "feature_sample_rate": ANALYSIS_SR,
            "lyrics_enabled": bool(do_lyrics),
        },
    }
    report["score"] = score_report(report)
    return report
