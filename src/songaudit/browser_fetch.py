"""Fetch the exact audio file a logged-in page streams.

The tool opens its own browser window with a persistent profile. The user logs
in there once and opens the song; from that point the stream is detected
automatically, the source file is saved bit-for-bit (no recording, no
re-encoding, no devices), and the audit runs on it.

Only use this on tracks you own or have permission to analyze.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

PROFILE_DIR = Path(os.environ.get("SONGAUDIT_BROWSER_PROFILE",
                                  Path.home() / ".songaudit" / "browser"))

AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aiff")
LOSSLESS_SUFFIXES = (".wav", ".flac", ".aiff")


def _collect(node, found: list) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                low = value.lower()
                is_audio_key = key in {"audio_url", "audioUrl", "wav_url", "stream_url", "download_url"}
                is_audio_link = low.startswith("http") and any(
                    low.split("?")[0].endswith(suffix) for suffix in AUDIO_SUFFIXES
                )
                if (is_audio_key or is_audio_link) and low.startswith("http") and "/api/forbidden" not in low:
                    found.append(value)
            else:
                _collect(value, found)
    elif isinstance(node, list):
        for item in node:
            _collect(item, found)


def _probe(path: Path) -> float:
    try:
        import soundfile as sf

        return float(sf.info(str(path)).duration)
    except Exception:
        return 0.0


def _label(url: str) -> str:
    parts = url.split("/")
    return parts[2] + "/" + parts[-1][:44]


def _rank(url: str, size: int) -> float:
    low = url.split("?")[0].lower()
    score = 0.0
    if low.endswith(LOSSLESS_SUFFIXES):
        score += 100
    elif low.endswith(".mp3"):
        score += 50
    score += min(size / 1_000_000, 50)
    return score


def fetch(url: str, out_path: str | Path, timeout: float = 600.0,
          channel: str | None = None, headless: bool = False,
          min_seconds: float = 20.0) -> Path:
    from playwright.sync_api import sync_playwright

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    state: dict = {"json": [], "media": []}

    def handle_response(response):
        try:
            headers = response.headers or {}
            content_type = (headers.get("content-type") or "").lower()
        except Exception:
            return
        if "json" in content_type and ("studio-api" in response.url or "suno.com" in response.url):
            try:
                payload = response.json()
            except Exception:
                return
            _collect(payload, state["json"])
        elif content_type.startswith("audio/") or response.url.split("?")[0].lower().endswith(
            AUDIO_SUFFIXES
        ):
            try:
                size = int(headers.get("content-length") or 0)
            except Exception:
                size = 0
            state["media"].append((size, response.url))

    with sync_playwright() as playwright:
        launch_channel = channel
        if launch_channel is None and sys.platform == "win32":
            launch_channel = "msedge"

        context = playwright.chromium.launch_persistent_context(
            str(PROFILE_DIR),
            channel=launch_channel,
            headless=headless,
            viewport={"width": 1280, "height": 900},
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.on("response", handle_response)

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass

        print("SongAudit browser is open. Log in once if asked, then press play on the track.",
              file=sys.stderr)
        print("Watching the stream for up to %d s..." % int(timeout), file=sys.stderr)

        started = time.time()
        deadline = started + timeout
        reloaded = False
        checked: set[str] = set()
        best_path: Path | None = None
        best_duration = 0.0
        best_url: str | None = None
        last_status = 0.0

        while time.time() < deadline:
            media = [u for _, u in sorted(state["media"], reverse=True)]
            candidates = []
            for item in state["json"] + media:
                if item not in candidates:
                    candidates.append(item)
            candidates.sort(key=lambda item: _rank(item, 0), reverse=True)

            for candidate in candidates[:6]:
                if candidate in checked:
                    continue
                checked.add(candidate)
                try:
                    response = context.request.get(candidate, timeout=180000)
                    if response.status >= 400:
                        continue
                    body = response.body()
                except Exception:
                    continue
                if len(body) < 120_000:
                    continue

                handle = tempfile.NamedTemporaryFile(delete=False, suffix=".bin")
                handle.write(body)
                handle.close()
                probe_path = Path(handle.name)
                duration = _probe(probe_path)
                print("  found %s  %.1f MB  %.1f s" % (
                    _label(candidate), len(body) / 1048576, duration), file=sys.stderr)

                if duration > best_duration:
                    if best_path is not None:
                        best_path.unlink(missing_ok=True)
                    best_path, best_duration, best_url = probe_path, duration, candidate
                else:
                    probe_path.unlink(missing_ok=True)

            if best_duration >= min_seconds:
                break

            if not reloaded and time.time() - started > 45:
                try:
                    page.reload()
                except Exception:
                    pass
                reloaded = True
                print("Reloaded the page after the login step.", file=sys.stderr)

            if time.time() - last_status > 10:
                last_status = time.time()
                print("  ... waiting (%d s)" % int(time.time() - started), file=sys.stderr)

            try:
                page.wait_for_timeout(1000)
            except Exception:
                print("Browser window was closed before the track finished.", file=sys.stderr)
                break

        if best_path is None or best_duration < min_seconds:
            if best_path is not None:
                best_path.unlink(missing_ok=True)
            try:
                context.close()
            except Exception:
                pass
            raise SystemExit(
                "No full track detected. Keep the SongAudit browser open, log in if asked, "
                "and press play on the song; then run it again."
            )

        suffix = Path(best_url.split("?")[0]).suffix or ".mp3"
        final = out_path.with_suffix(suffix)
        final.write_bytes(best_path.read_bytes())
        best_path.unlink(missing_ok=True)
        print("Captured %.1f s from %s" % (best_duration, _label(best_url)), file=sys.stderr)

        try:
            context.close()
        except Exception:
            pass

    print("Saved " + str(final), file=sys.stderr)
    return final
