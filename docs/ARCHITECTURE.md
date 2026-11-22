# Architecture

## Pipeline

    source (file / URL / loopback capture)
        |
        v
    ingest.py      resolve, stream to disk, size cap, metadata
        |
        v
    audio.py       libsndfile decode -> stereo float32 @ 44.1 kHz
        |
        +--> mastering.py   BS.1770 loudness, 4x true peak, clipping, DC, LRA, stereo
        +--> spectral.py    octave bands, tilt, rolloff, HPSS, codec cutoff
        +--> music.py       tempo, key, tuning, chroma-based sections
        +--> lyrics.py      optional faster-whisper transcript + vocal stats
        |
        v
    score.py       weighted rubric -> grade + ranked recommendations
        |
        v
    report.py      JSON + Markdown + single-file HTML (charts embedded)
        |
        +--> CLI   (songaudit audit)
        +--> Web   (FastAPI: upload -> job dir -> report)
        +--> API   (/report/{id}/json)

## Modules

| Module | Responsibility |
| --- | --- |
| ingest.py | Turn a path or URL into a local file; reject app-rendered pages; read tags. |
| audio.py | Decode to stereo float32, resample, mono fold-down. |
| mastering.py | Loudness (pyloudnorm), true peak, clipping runs, DC, quiet passages, stereo. |
| spectral.py | Long-term PSD, octave bands, tilt residual, rolloff, HPSS, cutoff. |
| music.py | Beat tracking, Krumhansl key estimation, tuning, agglomerative sections. |
| lyrics.py | Optional faster-whisper transcription and vocal statistics. |
| score.py | Deterministic rubric: category scores, grade, recommendations. |
| report.py | Jinja rendering and file output. |
| charts.py | Matplotlib figures encoded as base64 PNGs. |
| service.py | audit + render in one call, shared by CLI and web. |
| web.py | FastAPI routes and job storage. |
| capture.py | WASAPI/loopback recording for the "record what is playing" path. |

## Score model

| Category | Weight | Signals |
| --- | --- | --- |
| Loudness & dynamics | 30% | integrated LUFS vs -14, true peak vs -1 dBTP, clipping, LRA |
| Tonal balance | 20% | octave-band residuals against the track's own tilt, top-octave cutoff |
| Stereo image | 15% | correlation, mono fold-down loss, width |
| Cleanliness | 15% | quiet-passage floor, DC offset, edge silence |
| Musical clarity | 10% | tempo confidence, key confidence, tuning, section count |
| Vocal & lyrics | 10% | vocal coverage and words per minute (only when lyrics are enabled) |

Weights are renormalised when lyrics are disabled.

## Job layout

    data/jobs/<id>/
      source.<ext>      uploaded or downloaded audio
      report.html       self-contained report
      report.json       machine-readable measurements
      report.md         short summary

## Extension points

- New metric: add to the owning module, then surface it in the report template and (optionally) score it.
- New source: implement a resolver in ingest.py that returns a local path.
- New scorecard: rules live in score.py as pure functions of the report dict, so they are unit-testable.
