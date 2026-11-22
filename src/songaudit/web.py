"""FastAPI app: upload or link a track, get the audit back."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from . import __version__
from .config import AUDIO_EXTENSIONS, DATA_DIR, MAX_UPLOAD_BYTES
from .ingest import resolve_source, validate_url
from .service import audit_to_dir

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
JOBS = DATA_DIR / "jobs"


def create_app() -> FastAPI:
    app = FastAPI(title="SongAudit", version=__version__, docs_url="/api/docs")
    JOBS.mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        return TEMPLATES.TemplateResponse(
            request, "index.html", {"max_mb": MAX_UPLOAD_BYTES // (1024 * 1024)}
        )

    @app.post("/audit")
    async def create_audit(
        request: Request,
        file: UploadFile | None = File(None),
        url: str = Form(""),
        lyrics: str = Form(""),
    ):
        job_id = uuid.uuid4().hex
        job_dir = JOBS / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        do_lyrics = lyrics.lower() in {"1", "true", "on", "yes"}

        try:
            if file is not None and file.filename:
                suffix = Path(file.filename).suffix.lower()
                if suffix not in AUDIO_EXTENSIONS:
                    raise ValueError("Unsupported file type '" + (suffix or "?") + "'.")

                destination = job_dir / ("source" + suffix)
                size = 0
                with destination.open("wb") as handle:
                    while True:
                        chunk = await file.read(1 << 20)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > MAX_UPLOAD_BYTES:
                            raise ValueError("Upload is larger than the configured limit.")
                        handle.write(chunk)
                path, kind, label = destination, "upload", file.filename

            elif url.strip():
                validate_url(url.strip())
                path = await run_in_threadpool(resolve_source, url.strip(), job_dir)
                kind, label = "url", url.strip()

            else:
                raise ValueError("Provide an audio file or a direct audio URL.")

        except ValueError as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=400, detail=str(exc))

        try:
            await run_in_threadpool(
                audit_to_dir, path, job_dir, kind, label, do_lyrics,
                "/report/" + job_id + "/json",
            )
        except Exception as exc:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(status_code=500, detail="Analysis failed: " + str(exc))

        return RedirectResponse("/report/" + job_id, status_code=303)

    @app.get("/report/{job_id}", response_class=HTMLResponse)
    async def show_report(job_id: str):
        page = JOBS / job_id / "report.html"
        if not page.is_file():
            raise HTTPException(status_code=404, detail="Report not found.")
        return FileResponse(page, media_type="text/html")

    @app.get("/report/{job_id}/json")
    async def report_json(job_id: str):
        page = JOBS / job_id / "report.json"
        if not page.is_file():
            raise HTTPException(status_code=404, detail="Report not found.")
        return FileResponse(page, media_type="application/json")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
