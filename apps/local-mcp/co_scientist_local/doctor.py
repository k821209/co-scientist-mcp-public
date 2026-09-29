"""`python -m co_scientist_local doctor` — the system dependencies, by feature.

pip installs the Python side; the binaries and fonts some features shell out
to it cannot, and on a host where `sudo` asks for a password the agent can
never install them either. The only moment they get installed is when a
person runs setup — and setup never named them, so a 21-slide deck was
written with no PNG ever rendered (feedback 0a7d2981778e). This prints ✓/✗
per item with the install line, grouped by the feature that needs it, so a
person can run it before the first session and paste what is missing.
"""
from __future__ import annotations

import shutil
import sys


def _mod(name: str) -> bool:
    try:
        __import__(name)
        return True
    except Exception:  # noqa: BLE001 — a broken install counts as missing
        return False


def checks() -> list[dict]:
    from .tools.deck_render import render_requirements
    req = render_requirements()
    korean = req.get("korean_font")
    return [
        {"group": "export (export_to_path)", "what": "pandoc", "ok": bool(shutil.which("pandoc")),
         "install": "Debian/Ubuntu: sudo apt install -y pandoc · macOS: brew install pandoc",
         "why": "every .docx/.pdf export"},
        {"group": "export (export_to_path)", "what": "LibreOffice (soffice)", "ok": bool(req.get("soffice")),
         "install": "Debian/Ubuntu: sudo apt install -y libreoffice-writer · macOS: brew install --cask libreoffice",
         "why": "recommended — normalises .docx so Hancom Office opens it; export works without it"},
        {"group": "presentations (/paper-deck)", "what": "LibreOffice (soffice)", "ok": bool(req.get("soffice")),
         "install": "Debian/Ubuntu: sudo apt install -y libreoffice-impress · macOS: brew install --cask libreoffice",
         "why": "REQUIRED for any slide PNG/PDF — without it no preview renders at all"},
        {"group": "presentations (/paper-deck)", "what": "PyMuPDF (python module pymupdf)", "ok": bool(req.get("pymupdf")),
         "install": f"{sys.executable} -m pip install pymupdf",
         "why": "PDF → PNG; a declared dependency — missing means pip ran with --no-deps"},
        {"group": "presentations (/paper-deck), Korean text anywhere", "what": "a Korean font (fonts-noto-cjk)",
         "ok": korean is not False,
         "install": "Debian/Ubuntu: sudo apt install -y fonts-noto-cjk · macOS: built in",
         "why": "without it Korean renders as boxes and the PNG still looks like a success"},
        {"group": "video (/video-*)", "what": "ffmpeg", "ok": bool(shutil.which("ffmpeg")),
         "install": "Debian/Ubuntu: sudo apt install -y ffmpeg · macOS: brew install ffmpeg",
         "why": "chunk joins, last-frame extraction, every video pipeline step"},
        {"group": "video (/video-*)", "what": "vh (python module)", "ok": _mod("vh"),
         "install": "git clone https://github.com/k821209/co-scientist-video-harness.git ~/co-scientist-video-harness && "
                    f"{sys.executable} -m pip install -e ~/co-scientist-video-harness",
         "why": "only if you make videos"},
    ]


def cli(argv: list[str]) -> int:
    rows = checks()
    print(f"scivo doctor — {sys.executable}")
    group = None
    missing = 0
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            print(f"\n  [{group}]")
        mark = "✓" if r["ok"] else "✗"
        print(f"    {mark} {r['what']}  — {r['why']}")
        if not r["ok"]:
            missing += 1
            print(f"        install: {r['install']}")
    print()
    if missing:
        print(f"  {missing} missing. Only the feature groups you use matter; an agent cannot "
              "install system packages for you.")
    else:
        print("  everything present.")
    return 1 if ("--strict" in argv and missing) else 0
