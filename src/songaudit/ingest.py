"""Resolve a file path or URL into a local audio file and read its metadata."""

from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .config import AUDIO_EXTENSIONS, CONTENT_TYPE_EXTENSIONS, MAX_UPLOAD_BYTES

USER_AGENT = "SongAudit/0.1 (+https://github.com/ankurhalder/song-audit)"


def is_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def sha256_file(path: str | Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extension_from_url(url: str) -> str | None:
    suffix = Path(urlparse(url).path).suffix.lower()
    return suffix if suffix in AUDIO_EXTENSIONS else None


def validate_url(url: str) -> None:
    """Reject app-rendered pages that never expose a media file."""
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    if host.endswith("suno.com") or host.endswith("suno.ai"):
        raise ValueError(
            "Suno share pages are rendered by their app and do not expose the audio file. "
            "Open the track in Suno, download it (or record it with 'songaudit capture'), "
            "then upload the file here."
        )


def download(url: str, dest_dir: str | Path) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    with httpx.stream(
        "GET",
        url,
        follow_redirects=True,
        timeout=httpx.Timeout(60.0, read=180.0),
        headers={"User-Agent": USER_AGENT, "Accept": "audio/*,*/*;q=0.8"},
    ) as response:
        response.raise_for_status()
        content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
        allowed = content_type.startswith("audio/") or content_type in {
            "application/octet-stream", "binary/octet-stream", "",
        }
        if not allowed:
            raise ValueError(
                "That URL returned '" + (content_type or "unknown") + "', not audio. "
                "Link directly to an audio file or upload the track instead."
            )

        extension = _extension_from_url(url) or CONTENT_TYPE_EXTENSIONS.get(content_type) or ".mp3"
        stem = Path(urlparse(url).path).stem[:80] or "track"
        destination = dest_dir / (stem + extension)

        total = 0
        with destination.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 16):
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    handle.close()
                    destination.unlink(missing_ok=True)
                    raise ValueError("Download exceeds the configured size limit.")
                handle.write(chunk)

    return destination


def resolve_source(value: str, dest_dir: str | Path | None = None) -> Path:
    """Accept a local path or an http(s) URL and return a local file path."""
    if is_url(value):
        if dest_dir is None:
            raise ValueError("An output directory is required to download a URL.")
        return download(value, dest_dir)

    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("No such file: " + str(path))
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError("Unsupported audio extension: " + (path.suffix or "(none)"))
    return path


def read_tags(path: str | Path) -> dict:
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(str(path), easy=True)
        if audio is None:
            return {}
        tags = {}
        for key, value in audio.items():
            if isinstance(value, (list, tuple)):
                value = ", ".join(str(item) for item in value)
            tags[str(key)] = str(value)[:300]
        return tags
    except Exception:
        return {}
