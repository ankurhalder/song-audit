from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from songaudit.pipeline import audit_file
from songaudit.report import render_html, render_markdown, write_report
from songaudit.web import app


def test_report_renders(demo_wav):
    report = audit_file(demo_wav, source_label="demo.wav")
    html = render_html(report)
    assert "Scorecard" in html
    assert report["score"]["grade"] in html
    markdown = render_markdown(report)
    assert "SongAudit" in markdown
    assert "Recommended fixes" in markdown


def test_write_report_files(demo_wav, tmp_path):
    report = audit_file(demo_wav, source_label="demo.wav")
    paths = write_report(report, tmp_path)
    assert paths["html"].is_file()
    assert paths["json"].is_file()
    assert paths["markdown"].is_file()


def test_web_upload_flow(demo_wav):
    client = TestClient(app)
    with open(demo_wav, "rb") as handle:
        response = client.post(
            "/audit",
            files={"file": ("demo.wav", handle, "audio/wav")},
            data={"url": "", "lyrics": ""},
            follow_redirects=False,
        )
    assert response.status_code == 303
    location = response.headers["location"]
    page = client.get(location)
    assert page.status_code == 200
    assert "Scorecard" in page.text

    report = client.get(location + "/json")
    assert report.status_code == 200
    assert report.json()["score"]["grade"]


def test_health():
    client = TestClient(app)
    assert client.get("/healthz").json()["status"] == "ok"
