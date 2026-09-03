#!/usr/bin/env python3
"""Bundle the app into one HTML file: timecards/dist/ram-timecard.html.

One file that opens from an email attachment, a Teams message, a USB stick or a private artifact link, with the job,
cost code and equipment lists baked in. It saves to the phone the same way as the hosted app. The hosted app
(timecards/app on GitHub Pages) is the real distribution: it updates itself and installs to the home screen. The
single file is for trying it out and for a phone with no browser install rights.

    python3 timecards/tools/build_single.py            # writes dist/ram-timecard.html
    python3 tools/build_single.py --fragment           # body-only fragment (no <html>/<head>) for an artifact host
"""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"


def build(fragment: bool = False) -> str:
    html = (APP / "index.html").read_text(encoding="utf-8")
    css = (APP / "styles.css").read_text(encoding="utf-8")
    js = (APP / "app.js").read_text(encoding="utf-8").replace("</script", "<\\/script")
    ref = (APP / "data" / "reference.json").read_text(encoding="utf-8").strip().replace("</script", "<\\/script")
    icon = base64.b64encode((APP / "icons" / "icon-192.png").read_bytes()).decode()
    body = re.search(r"<body>(.*)</body>", html, re.S).group(1)
    body = body.replace('<script src="app.js"></script>', f"<script>window.__RAMTC_REF = {ref};</script>\n<script>\n{js}\n</script>")
    head_bits = f"<title>RAM Timecard</title>\n<style>\n{css}\n</style>"
    if fragment:
        return f"{head_bits}\n{body}\n"
    head = re.search(r"<head>(.*)</head>", html, re.S).group(1)
    head = re.sub(r'<link rel="manifest"[^>]*>\n?', "", head)
    head = re.sub(r'<link rel="stylesheet"[^>]*>', f"<style>\n{css}\n</style>", head)
    head = re.sub(r'<link rel="apple-touch-icon" href="[^"]*">', f'<link rel="apple-touch-icon" href="data:image/png;base64,{icon}">', head)
    head = re.sub(r'<link rel="icon" href="[^"]*">', f'<link rel="icon" href="data:image/png;base64,{icon}">', head)
    return f"<!doctype html>\n<html lang=\"en-CA\">\n<head>{head}</head>\n<body>{body}</body>\n</html>\n"


if __name__ == "__main__":
    frag = "--fragment" in sys.argv
    out = ROOT / "dist" / ("ram-timecard.fragment.html" if frag else "ram-timecard.html")
    out.parent.mkdir(exist_ok=True)
    out.write_text(build(frag), encoding="utf-8")
    print(f"{out} ({out.stat().st_size // 1024} KB)")
