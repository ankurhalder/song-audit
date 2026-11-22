from __future__ import annotations

import json
import math

from songaudit.audio import load_audio, to_mono
from songaudit.mastering import analyze_mastering, analyze_stereo
from songaudit.music import analyze_music, estimate_tempo
from songaudit.pipeline import audit_file
from songaudit.spectral import analyze_spectral


def test_clipping_is_detected(clipped_wav):
    audio = load_audio(clipped_wav)
    result = analyze_mastering(audio.samples, audio.sample_rate)
    assert result["clipping"]["count"] > 0
    assert result["clipping"]["percent"] > 0


def test_demo_track_loudness_and_stereo(demo_wav):
    audio = load_audio(demo_wav)
    result = analyze_mastering(audio.samples, audio.sample_rate)
    assert -30 < result["integrated_lufs"] < 0
    assert result["duration_s"] > 10

    stereo = analyze_stereo(audio.samples)
    assert -1.0 <= stereo["correlation"] <= 1.0
    assert 0 <= stereo["width_percent"] <= 100


def test_tempo_estimate(click_wav):
    audio = load_audio(click_wav)
    mono = to_mono(audio.samples)
    tempo = estimate_tempo(mono, audio.sample_rate)
    candidates = [tempo["bpm"], tempo["bpm"] * 2, tempo["bpm"] / 2]
    assert any(abs(value - 120.0) < 3.0 for value in candidates)


def test_spectral_bands_sum_sensibly(demo_wav):
    audio = load_audio(demo_wav)
    mono = to_mono(audio.samples)
    spectral = analyze_spectral(mono, audio.sample_rate)
    assert spectral["bands"]
    assert spectral["nyquist_hz"] > 0
    assert math.isfinite(spectral["tilt_db_per_octave"])


def test_full_pipeline_smoke(demo_wav):
    report = audit_file(demo_wav, source_kind="test", source_label="demo.wav")
    assert report["score"]["overall"] >= 0
    assert report["score"]["grade"]
    assert report["mastering"]["integrated_lufs"] < 0
    assert report["music"]["sections"]
    assert report["source"]["sha256"]
    assert json.dumps(report)  # must be JSON serializable


def test_music_sections_cover_track(demo_wav):
    audio = load_audio(demo_wav)
    mono = to_mono(audio.samples)
    music = analyze_music(mono[: audio.sample_rate * 12], audio.sample_rate)
    assert music["section_count"] >= 1
    previous_end = 0.0
    for section in music["sections"]:
        assert section["start_s"] >= previous_end - 0.01
        previous_end = section["end_s"]
