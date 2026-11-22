"""One-shot helpers shared by the CLI and the web app."""

from __future__ import annotations

from pathlib import Path

from .audio import load_audio, to_mono
from .pipeline import audit_file
from .report import write_report


def audit_to_dir(source_path: str | Path, out_dir: str | Path, source_kind: str = "file",
                 label: str | None = None, do_lyrics: bool = False,
                 json_url: str | None = None) -> tuple[dict, dict]:
    report = audit_file(source_path, source_kind=source_kind, source_label=label,
                        do_lyrics=do_lyrics)
    audio = load_audio(str(source_path))
    paths = write_report(report, out_dir, to_mono(audio.samples), audio.sample_rate,
                         json_url=json_url)
    return report, paths
