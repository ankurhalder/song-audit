"""Render the audit as a self-contained HTML report, JSON and Markdown."""

from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATE_DIR = Path(__file__).parent / "templates"


def tone_for(overall: float) -> tuple[str, str]:
    if overall >= 85:
        return "release ready", "#34d399"
    if overall >= 70:
        return "good shape", "#8b5cf6"
    if overall >= 55:
        return "needs work", "#f59e0b"
    return "not ready", "#ef4444"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_html(report: dict, charts: dict | None = None, json_url: str | None = None) -> str:
    template = _environment().get_template("report.html")
    tone, color = tone_for(report["score"]["overall"])
    title = report.get("tags", {}).get("title") or report["source"]["filename"]
    artist = report.get("tags", {}).get("artist") or "Unknown artist"
    return template.render(
        r=report,
        charts=charts or {},
        json_url=json_url,
        tone=tone,
        grade_color=color,
        title=title,
        artist=artist,
    )


def render_markdown(report: dict) -> str:
    score = report["score"]
    mastering = report["mastering"]
    music = report["music"]
    name = report.get("tags", {}).get("title") or report["source"]["filename"]
    lines = [
        "# SongAudit - " + name,
        "",
        "**Grade " + score["grade"] + " (" + str(score["overall"]) + "/100)** - " + score["headline"],
        "",
        "| Category | Score | Notes |",
        "| --- | --- | --- |",
    ]
    for category in score["categories"]:
        lines.append(
            "| " + category["label"] + " | " + str(category["score"]) + " | " + category["note"] + " |"
        )
    lines += [
        "",
        "- Duration: " + str(report["file"]["duration_s"]) + " s",
        "- Loudness: " + str(mastering["integrated_lufs"]) + " LUFS, true peak " +
        str(mastering["true_peak_db"]) + " dBTP",
        "- Tempo: " + str(music["bpm"]) + " BPM, key " + music["key"],
        "- Sections: " + str(music["section_count"]),
        "- SHA-256: " + report["source"]["sha256"],
        "",
        "## Recommended fixes",
        "",
    ]
    if score["recommendations"]:
        for item in score["recommendations"]:
            lines.append("- **" + item["title"] + "** (" + item["severity"] + ") - " + item["fix"])
    else:
        lines.append("- Nothing blocking. Ship it.")
    lines.append("")
    return "\n".join(lines)


def write_report(report: dict, out_dir: str | Path, mono=None, sr: int | None = None,
                 json_url: str | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    charts = {}
    if mono is not None and sr is not None:
        from .charts import build_charts

        charts = build_charts(report, mono, sr)

    html = render_html(report, charts=charts, json_url=json_url)
    (out_dir / "report.html").write_text(html, encoding="utf-8")
    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")

    return {
        "html": out_dir / "report.html",
        "json": out_dir / "report.json",
        "markdown": out_dir / "report.md",
    }
