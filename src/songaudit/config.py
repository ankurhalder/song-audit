"""Runtime configuration pulled from environment variables."""

from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("SONGAUDIT_DATA_DIR", "data")).resolve()
MAX_UPLOAD_BYTES = int(os.environ.get("SONGAUDIT_MAX_UPLOAD_MB", "100")) * 1024 * 1024
TARGET_SR = int(os.environ.get("SONGAUDIT_SAMPLE_RATE", "44100"))
ANALYSIS_SR = 22050
JOB_TTL_HOURS = int(os.environ.get("SONGAUDIT_JOB_TTL_HOURS", "24"))

AUDIO_EXTENSIONS = {
    ".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".webm",
}

CONTENT_TYPE_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/mp4": ".m4a",
    "audio/aac": ".m4a",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
}
