"""Command line interface: audit, serve, capture."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .ingest import is_url, resolve_source, validate_url
from .service import audit_to_dir


def _slug(value: str) -> str:
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_") else "-" for ch in value)
    return "-".join(part for part in cleaned.split("-") if part)[:60] or "audit"


def _print_summary(report: dict, paths: dict) -> None:
    score = report["score"]
    mastering = report["mastering"]
    music = report["music"]
    print("")
    print("  SongAudit " + __version__)
    print("  " + "-" * 46)
    print("  Grade        " + score["grade"] + "  (" + str(score["overall"]) + "/100)")
    print("  " + score["headline"])
    print("  Loudness     " + str(mastering["integrated_lufs"]) + " LUFS / " +
          str(mastering["true_peak_db"]) + " dBTP")
    print("  Tempo / key  " + str(music["bpm"]) + " BPM / " + music["key"])
    print("  Issues       " + str(len(score["recommendations"])))
    print("  " + "-" * 46)
    print("  HTML   " + str(paths["html"]))
    print("  JSON   " + str(paths["json"]))
    print("  MD     " + str(paths["markdown"]))
    print("")


def cmd_audit(args: argparse.Namespace) -> int:
    out_dir = Path(args.out) if args.out else Path("reports") / _slug(
        Path(args.source).stem if not is_url(args.source) else "audit"
    )
    source_kind = "url" if is_url(args.source) else "file"

    try:
        if is_url(args.source):
            validate_url(args.source)
            path = resolve_source(args.source, out_dir / "source")
        else:
            path = resolve_source(args.source)
    except (ValueError, FileNotFoundError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2

    try:
        report, paths = audit_to_dir(path, out_dir, source_kind,
                                     path.name if source_kind == "file" else args.source,
                                     args.lyrics)
    except RuntimeError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_summary(report, paths)

    if args.open:
        webbrowser.open(paths["html"].resolve().as_uri())
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    print("SongAudit on http://" + args.host + ":" + str(args.port), file=sys.stderr)
    uvicorn.run("songaudit.web:app", host=args.host, port=args.port, log_level="info")
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    from .browser_fetch import fetch

    out_dir = Path(args.out) if args.out else Path("reports") / _slug("song")
    try:
        track = fetch(args.url, out_dir / "source" / "track.mp3", timeout=args.timeout,
                      channel=args.browser, headless=False)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    report, paths = audit_to_dir(track, out_dir, "browser", args.url, args.lyrics)
    _print_summary(report, paths)
    webbrowser.open(paths["html"].resolve().as_uri())
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    from .browser_fetch import fetch

    try:
        fetch(args.url, args.out, timeout=args.timeout,
              channel=args.browser, headless=args.headless)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    from .capture import capture

    output = args.output or "capture.wav"
    try:
        path = capture(output, seconds=args.seconds, device=args.device,
                       wait_for_start=args.wait, wait_timeout=args.wait_timeout)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print("Saved " + path, file=sys.stderr)
    if args.audit:
        out_dir = Path(args.out) if args.out else Path("reports") / _slug(Path(path).stem)
        report, paths = audit_to_dir(path, out_dir, "capture", Path(path).name, args.lyrics)
        _print_summary(report, paths)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="songaudit", description="Full audit for any song.")
    parser.add_argument("--version", action="version", version="songaudit " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="Analyze a file or direct audio URL.")
    audit.add_argument("source", help="Path to an audio file, or a direct https audio URL.")
    audit.add_argument("-o", "--out", help="Output directory (default: reports/<name>).")
    audit.add_argument("--lyrics", action="store_true", help="Transcribe vocals (optional extra).")
    audit.add_argument("--json", action="store_true", help="Print the full report JSON.")
    audit.add_argument("--open", action="store_true", help="Open the HTML report when done.")
    audit.set_defaults(func=cmd_audit)

    serve = sub.add_parser("serve", help="Run the local web app.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(func=cmd_serve)

    opener = sub.add_parser("open", help="Open a song in the built-in browser, save the source file, audit it.")
    opener.add_argument("url")
    opener.add_argument("-o", "--out", help="Output directory (default: reports/song).")
    opener.add_argument("--timeout", type=float, default=600.0)
    opener.add_argument("--browser", default=None, help="Browser channel, e.g. msedge or chrome.")
    opener.add_argument("--lyrics", action="store_true")
    opener.set_defaults(func=cmd_open)

    fetch = sub.add_parser("fetch", help="Save a track from a page behind a login (uses a local browser).")
    fetch.add_argument("url")
    fetch.add_argument("-o", "--out", default="inbox/track.mp3")
    fetch.add_argument("--timeout", type=float, default=300.0)
    fetch.add_argument("--browser", default=None, help="Browser channel, e.g. msedge or chrome.")
    fetch.add_argument("--headless", action="store_true")
    fetch.set_defaults(func=cmd_fetch)

    capture = sub.add_parser("capture", help="Record what this machine is playing, then audit it.")
    capture.add_argument("--output", help="Where to write the recording (default: capture.wav).")
    capture.add_argument("--seconds", type=float, default=None, help="Hard stop after N seconds.")
    capture.add_argument("--device", default=None, help="Loopback device name substring.")
    capture.add_argument("--wait", action="store_true",
                         help="Arm the recorder and start writing only when audio plays.")
    capture.add_argument("--wait-timeout", type=float, default=300.0,
                         help="Give up waiting for playback after N seconds (default 300).")
    capture.add_argument("--audit", action="store_true", help="Run the audit after recording.")
    capture.add_argument("--out", help="Audit output directory (with --audit).")
    capture.add_argument("--lyrics", action="store_true")
    capture.set_defaults(func=cmd_capture)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
