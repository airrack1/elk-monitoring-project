"""Generate the offline single-file web app from the Python source of truth.

`web_static/standalone.html` embeds the checklist template and the runner
allowlist so the app works with no server behind it. Rather than hand-copying
that data into JavaScript (where it would silently rot), we generate it here
from `checklist_template.py` and `runner.RUNNERS`.

    python -m netaudit.tools.build_standalone          # rewrite standalone.html
    python -m netaudit.tools.build_standalone --check  # verify it is in sync

`tests/test_standalone.py` runs the --check path, so a checklist edit that
isn't rebuilt fails CI instead of shipping a stale phone UI.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

from ..data import checklist_template as tmpl
from ..runner import RUNNERS

STATIC_DIR = Path(__file__).resolve().parent.parent / "web_static"
SRC = STATIC_DIR / "standalone.src.html"
OUT = STATIC_DIR / "standalone.html"
PLACEHOLDER = "/*__NETAUDIT_DATA__*/"

# Colours reused for the home-screen icon (matches the app's dark palette).
_BG = (11, 18, 32)
_ACCENT = (79, 156, 255)


def build_data() -> dict:
    """The JSON payload embedded in the page — same shape as `/api/template`."""
    items_by_phase = tmpl.build_phase_items()
    return {
        "generator": "netaudit.tools.build_standalone",
        "template": {
            "version": tmpl.TEMPLATE_VERSION,
            "phases": [
                {
                    "number": p["number"],
                    "name": p["name"],
                    "intent": p["intent"],
                    "optional": p.get("optional", False),
                    "tools": p["tools"],
                    "items": [
                        {"id": iid, "text": txt} for iid, txt in items_by_phase[p["number"]]
                    ],
                }
                for p in tmpl.PHASES
            ],
            "qa": [{"id": f"qa.{i}", "text": t} for i, t in enumerate(tmpl.FINAL_QA, 1)],
        },
        # Deliberately no "installed" flag: that is host-specific and the
        # browser has no PATH to check.
        "runners": [
            {
                "name": name,
                "phase": spec["phase"],
                "binary": spec["binary"],
                "args": spec["args"],
                "desc": spec["desc"],
            }
            for name, spec in sorted(RUNNERS.items(), key=lambda kv: (kv[1]["phase"], kv[0]))
        ],
    }


# --- home-screen icon -------------------------------------------------------

def _png(width: int, height: int, pixels: bytes) -> bytes:
    """Minimal RGB PNG encoder (stdlib only)."""
    raw = b"".join(
        b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height)
    )

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def icon_data_uri(size: int = 180) -> str:
    """A reticle glyph — 'scope-guarded' in one mark — as a data: URI."""
    c = size / 2.0
    ring_outer, ring_inner = size * 0.40, size * 0.33
    dot = size * 0.07
    tick_len, tick_half = size * 0.12, size * 0.022
    px = bytearray()
    for y in range(size):
        for x in range(size):
            dx, dy = x + 0.5 - c, y + 0.5 - c
            r = (dx * dx + dy * dy) ** 0.5
            on = ring_inner <= r <= ring_outer or r <= dot
            if not on:  # crosshair ticks reaching in from each edge
                if abs(dy) <= tick_half and (
                    x < tick_len or x > size - tick_len
                ):
                    on = True
                elif abs(dx) <= tick_half and (
                    y < tick_len or y > size - tick_len
                ):
                    on = True
            px.extend(_ACCENT if on else _BG)
    import base64

    return "data:image/png;base64," + base64.b64encode(_png(size, size, bytes(px))).decode()


# --- assembly ---------------------------------------------------------------

def render_body() -> str:
    """The page content (no <html>/<head>/<body> wrapper), data injected."""
    src = SRC.read_text(encoding="utf-8")
    if PLACEHOLDER not in src:
        raise SystemExit(f"placeholder {PLACEHOLDER} missing from {SRC}")
    payload = json.dumps(build_data(), indent=1, sort_keys=False)
    # </script> inside a JSON string would close the tag early.
    payload = payload.replace("</", "<\\/")
    return src.replace(PLACEHOLDER, payload)


def render_document() -> str:
    """A complete, standalone HTML file — servable or openable from disk."""
    icon = icon_data_uri()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0b1220" media="(prefers-color-scheme: dark)">
<meta name="theme-color" content="#f4f6fb" media="(prefers-color-scheme: light)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="netaudit">
<meta name="mobile-web-app-capable" content="yes">
<meta name="robots" content="noindex, nofollow">
<title>netaudit — offline engagement control</title>
<link rel="apple-touch-icon" href="{icon}">
<link rel="icon" href="{icon}">
</head>
<body>
<!-- GENERATED FILE — edit standalone.src.html, then run:
     python -m netaudit.tools.build_standalone -->
{render_body()}
</body>
</html>
"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Build the offline single-file web app.")
    ap.add_argument("--check", action="store_true",
                    help="Exit non-zero if standalone.html is out of date.")
    ap.add_argument("--body-out", help="Also write the bare page content here.")
    args = ap.parse_args(argv)

    doc = render_document()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != doc:
            print("standalone.html is out of date — run "
                  "`python -m netaudit.tools.build_standalone`", file=sys.stderr)
            return 1
        print("standalone.html is up to date.")
        return 0

    OUT.write_text(doc, encoding="utf-8")
    print(f"wrote {OUT} ({len(doc):,} bytes)")
    if args.body_out:
        Path(args.body_out).write_text(render_body(), encoding="utf-8")
        print(f"wrote {args.body_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
