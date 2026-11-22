"""Turn raw measurements into a weighted scorecard and a prioritized fix list."""

from __future__ import annotations

from .util import clamp

WEIGHTS = {
    "loudness": 0.30,
    "tonal": 0.20,
    "stereo": 0.15,
    "cleanliness": 0.15,
    "musical": 0.10,
    "lyrics": 0.10,
}

LABELS = {
    "loudness": "Loudness & dynamics",
    "tonal": "Tonal balance",
    "stereo": "Stereo image",
    "cleanliness": "Cleanliness",
    "musical": "Musical clarity",
    "lyrics": "Vocal & lyrics",
}


def grade_for(overall: float) -> str:
    if overall >= 95:
        return "A+"
    if overall >= 90:
        return "A"
    if overall >= 85:
        return "A-"
    if overall >= 80:
        return "B+"
    if overall >= 75:
        return "B"
    if overall >= 70:
        return "B-"
    if overall >= 65:
        return "C+"
    if overall >= 60:
        return "C"
    if overall >= 50:
        return "D"
    return "F"


def _rec(severity: str, category: str, title: str, detail: str, fix: str) -> dict:
    return {"severity": severity, "category": category, "title": title, "detail": detail, "fix": fix}


def score_report(report: dict) -> dict:
    mastering = report["mastering"]
    stereo = report["stereo"]
    spectral = report["spectral"]
    music = report["music"]
    lyrics = report.get("lyrics")

    recommendations: list[dict] = []

    # ---------------------------------------------------------------- loudness
    lufs = mastering["integrated_lufs"]
    true_peak = mastering["true_peak_db"]
    clipping = mastering["clipping"]["percent"]
    lra = mastering["loudness_range_lu"]

    s_lufs = clamp(100 - 6 * abs(lufs + 14), 0, 100)
    s_peak = 100.0 if true_peak <= -1.0 else clamp(100 - 18 * (true_peak + 1), 0, 100)
    s_clip = 100.0 if clipping <= 0 else 100.0 / (1.0 + 200.0 * clipping)
    if lra < 6:
        s_lra = clamp(100 - (6 - lra) * 12, 0, 100)
    elif lra > 12:
        s_lra = clamp(100 - (lra - 12) * 6, 0, 100)
    else:
        s_lra = 100.0
    loudness_score = 0.40 * s_lufs + 0.25 * s_peak + 0.20 * s_clip + 0.15 * s_lra

    if true_peak > -0.9:
        recommendations.append(_rec(
            "high" if true_peak > 0 else "medium", "loudness",
            "True peak is " + str(true_peak) + " dBTP",
            "Inter-sample peaks above -1 dBTP can clip after lossy encoding and on consumer DACs.",
            "Lower the limiter ceiling by about 1 dB (target -1.0 dBTP or lower).",
        ))
    if clipping > 0:
        recommendations.append(_rec(
            "high", "loudness",
            str(clipping) + "% of samples are clipped",
            "The encoder is already removing peaks, which adds distortion and dulls transients.",
            "Reduce gain into the limiter and re-bounce with a true-peak limiter.",
        ))
    if lufs > -11:
        recommendations.append(_rec(
            "medium", "loudness",
            "Master is louder than streaming targets",
            "At " + str(lufs) + " LUFS the track is " + str(round(-14 - lufs, 1)) +
            " LU above the -14 LUFS streaming reference, so platforms will turn it down.",
            "Aim for -14 LUFS integrated (or -9 to -11 only for club/vinyl deliverables).",
        ))
    elif lufs < -17:
        recommendations.append(_rec(
            "medium", "loudness",
            "Master is quieter than streaming targets",
            "At " + str(lufs) + " LUFS it will feel soft next to -14 LUFS references.",
            "Raise level into the limiter, or normalize to -14 LUFS for streaming delivery.",
        ))
    if lra < 4:
        recommendations.append(_rec(
            "medium", "loudness",
            "Very little loudness movement",
            "A loudness range of " + str(lra) + " LU suggests heavy bus compression and a flat dynamic arc.",
            "Ease off bus compression and let choruses lift a few dB above verses.",
        ))

    # ------------------------------------------------------------------- tonal
    deviations = spectral.get("deviations_db", {})
    penalty = 0.0
    presence = deviations.get("presence", 0.0)
    low_mid = deviations.get("low_mid", 0.0)
    bass = deviations.get("bass", 0.0)
    air = deviations.get("air", 0.0)

    if presence > 5:
        penalty += (presence - 5) * 9
        recommendations.append(_rec(
            "medium", "tonal",
            "Presence band sits " + str(presence) + " dB above the track tilt",
            "2-6 kHz is where sibilance and harshness live; too much reads as fatiguing, especially on phones.",
            "Try a broad 1-2 dB cut around 2.5-4 kHz and re-check on small speakers.",
        ))
    if low_mid > 5:
        penalty += (low_mid - 5) * 8
        recommendations.append(_rec(
            "medium", "tonal",
            "Low-mids sit " + str(low_mid) + " dB above the track tilt",
            "120-500 Hz build-up masks vocals and makes the mix feel muddy.",
            "Cut 1-2 dB around 200-400 Hz on guitars/keys, or high-pass pads harder.",
        ))
    if bass > 5:
        penalty += (bass - 5) * 8
        recommendations.append(_rec(
            "low", "tonal",
            "Sub/bass sits " + str(bass) + " dB above the track tilt",
            "A strong low end is fine for club music, but it eats headroom on streaming loudness normalization.",
            "Check the 40-80 Hz region in mono and trim if the kick/sub overlap.",
        ))
    if air < -8:
        penalty += min(20.0, (-air - 8) * 5)
        recommendations.append(_rec(
            "low", "tonal",
            "Top end is darker than the track tilt",
            "10-16 kHz is " + str(air) + " dB below the fitted tilt, which can read as dull or closed.",
            "A gentle high shelf above 10 kHz can restore air without harshness.",
        ))
    tonal_score = clamp(100 - penalty, 0, 100)

    # ------------------------------------------------------------------ stereo
    correlation = stereo["correlation"]
    mono_loss = stereo["mono_loss_db"]
    width = stereo["width_percent"]
    s_stereo = 100.0
    if correlation < 0:
        s_stereo -= min(55.0, -correlation * 85)
        recommendations.append(_rec(
            "high", "stereo",
            "Channels are negatively correlated",
            "Correlation of " + str(correlation) + " means parts of the mix cancel in mono (phones, club, TVs).",
            "Check polarity, wide modulation effects and doubled parts; keep bass and kick mono.",
        ))
    if correlation > 0.95:
        s_stereo -= (correlation - 0.95) * 250
        recommendations.append(_rec(
            "low", "stereo",
            "Image is nearly mono",
            "Correlation of " + str(correlation) + " leaves little width on headphones.",
            "Widen pads/keys with gentle stereo imaging, keeping lead vocal and bass centred.",
        ))
    if mono_loss < -3:
        s_stereo -= min(45.0, (-mono_loss - 3) * 12)
        recommendations.append(_rec(
            "medium", "stereo",
            "Mono fold-down loses " + str(abs(mono_loss)) + " dB",
            "The stereo sum is noticeably quieter than the channels, a sign of phase cancellation.",
            "Check the mix in mono and fix polarity or timing on doubled layers.",
        ))
    if stereo["channels"] == 2 and width < 6:
        s_stereo -= 8
    stereo_score = clamp(s_stereo, 0, 100)

    # ------------------------------------------------------------- cleanliness
    quiet = mastering["quiet_passage_db"]
    dc = max((abs(v) for v in mastering["dc_offset"]), default=0.0)
    s_clean = 100.0
    if dc > 0.002:
        s_clean -= min(20.0, (dc - 0.002) * 4000)
    if mastering["head_silence_s"] > 3 or mastering["tail_silence_s"] > 3:
        s_clean -= 4
    clean_score = clamp(s_clean, 0, 100)

    # ----------------------------------------------------------------- musical
    s_tempo = 100 * music["tempo_confidence"]
    s_key = 100 * music["key_confidence"]
    s_tune = clamp(100 - abs(music["tuning_cents"]) * 3, 0, 100)
    sections = music["section_count"]
    s_struct = 100.0 if 3 <= sections <= 8 else (55.0 if sections < 3 else 70.0)
    if sections < 3:
        recommendations.append(_rec(
            "low", "musical",
            "Only " + str(sections) + " structural section(s) detected",
            "A single flat section usually means the arrangement lacks contrast or the detector found little novelty.",
            "Add a distinct intro/chorus or check that the arrangement actually changes energy.",
        ))
    if music["tempo_confidence"] < 0.35:
        recommendations.append(_rec(
            "low", "musical",
            "Tempo is ambiguous",
            "The beat tracker could not lock on confidently (" + str(music["tempo_confidence"]) + ").",
            "Check for free-time passages or an unclear transient pattern in the drums.",
        ))
    if abs(music["tuning_cents"]) > 15:
        recommendations.append(_rec(
            "low", "musical",
            "Ensemble tuning is off by " + str(music["tuning_cents"]) + " cents",
            "Consistent detuning can make the track feel uneasy, especially with acoustic instruments.",
            "Check the reference pitch of sampled instruments and vocal tuning.",
        ))
    if music.get("hard_ending"):
        recommendations.append(_rec(
            "low", "musical",
            "Abrupt ending",
            "The track stops at full level with no fade or reverb tail.",
            "Add a short fade or let the final chord ring for a natural release.",
        ))
    musical_score = 0.30 * s_tempo + 0.30 * s_key + 0.20 * s_tune + 0.20 * s_struct

    # ------------------------------------------------------------------ lyrics
    lyric_score = None
    if lyrics:
        coverage = clamp(lyrics.get("vocal_coverage", 0.0), 0.0, 1.0)
        wpm = lyrics.get("words_per_minute", 0)
        s_cov = clamp(coverage * 140, 0, 100)
        s_flow = 100.0 if 55 <= wpm <= 180 else clamp(100 - abs(wpm - 115) * 0.6, 0, 100)
        lyric_score = 0.6 * s_cov + 0.4 * s_flow
        if coverage < 0.35:
            recommendations.append(_rec(
                "low", "lyrics",
                "Little vocal content detected",
                "Only " + str(round(coverage * 100)) + "% of the track contains transcribed speech.",
                "If the track is instrumental, disregard this; otherwise check the vocal level in the mix.",
            ))

    categories: list[dict] = []
    scores = {
        "loudness": loudness_score,
        "tonal": tonal_score,
        "stereo": stereo_score,
        "cleanliness": clean_score,
        "musical": musical_score,
    }
    if lyric_score is not None:
        scores["lyrics"] = lyric_score

    weight_total = sum(WEIGHTS[key] for key in scores)
    overall = sum(scores[key] * WEIGHTS[key] for key in scores) / weight_total

    notes = {
        "loudness": str(lufs) + " LUFS / " + str(true_peak) + " dBTP / " + str(lra) + " LU range",
        "tonal": "tilt " + str(spectral["tilt_db_per_octave"]) + " dB/oct, presence " +
                 str(deviations.get("presence", 0)) + " dB residual",
        "stereo": "correlation " + str(correlation) + ", width " + str(width) + "%",
        "cleanliness": "noise floor " + str(quiet) + " dBFS",
        "musical": str(music["bpm"]) + " BPM, " + str(music["key"]) + ", " + str(sections) + " sections",
        "lyrics": str(round((lyrics or {}).get("vocal_coverage", 0) * 100)) + "% vocal coverage",
    }

    for key, value in scores.items():
        categories.append({
            "id": key,
            "label": LABELS[key],
            "score": round(value, 1),
            "weight": WEIGHTS[key],
            "note": notes[key],
        })

    severity_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda r: severity_order.get(r["severity"], 3))

    # A master this far from the streaming target cannot be called "release ready".
    delta = abs(lufs + 14)
    if delta > 10:
        overall = min(overall, 74.0)
    elif delta > 6:
        overall = min(overall, 84.0)

    overall = round(overall, 1)
    grade = grade_for(overall)
    headline = {
        "A+": "Release-ready. Nothing blocking.",
        "A": "Release-ready with minor polish.",
        "A-": "Strong master with a couple of small fixes.",
        "B+": "Good master, a few meaningful improvements left.",
        "B": "Solid, but several fixes would lift it.",
        "B-": "Workable; the fix list matters.",
        "C+": "Needs work before release.",
        "C": "Needs work before release.",
        "D": "Significant issues to fix.",
        "F": "Not release-ready yet.",
    }[grade]

    return {
        "overall": overall,
        "grade": grade,
        "headline": headline,
        "categories": categories,
        "recommendations": recommendations,
        "weights": {key: WEIGHTS[key] for key in scores},
    }
