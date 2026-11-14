"""`python -m co_scientist_local doctor` — the system dependencies, by feature.

pip installs the Python side; the binaries and fonts some features shell out
to it cannot, and on a host where `sudo` asks for a password the agent can
never install them either. The only moment they get installed is when a
person runs setup — and setup never named them, so a 21-slide deck was
written with no PNG ever rendered (feedback 0a7d2981778e). This prints ✓/✗
per item with the install line, grouped by the feature that needs it, so a
person can run it before the first session and paste what is missing.

That was a command a person had to know to run. `machine_report()` is the same
list for the SESSION: `whoami()` carries it, so an agent — and the harness's
briefing — knows before the work starts that this machine cannot export a
.docx, instead of finding out forty minutes in. Measured on the development
machine itself, 2026-11-14: pandoc was not installed, and no session had ever
been told.

Every program the package looks for belongs in `checks()`: a test reads the
source for `shutil.which(...)` and fails on a name no row stands for. The
list used to be kept by hand, and the headless browser `preview_study` needs
was never added to it.
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
    """One row per thing a feature needs from the machine.

    `ok` is True, False, or None — None is "could not tell", and it is not
    shown as present: the Korean-font row read `ok` whenever `fc-list` was
    missing, which is the machine most likely to lack the font too.
    `programs` are the names the row stands for on PATH (what the coverage
    test matches); `needed` is `required` when the feature does not work at
    all without it.
    """
    from .tools.deck_render import render_requirements
    from .tools.study_preview import _BROWSERS, find_browser
    req = render_requirements()
    korean = req.get("korean_font")
    return [
        {"group": "export (export_to_path)", "what": "pandoc", "ok": bool(shutil.which("pandoc")),
         "programs": ("pandoc",), "needed": "required",
         "install": "Debian/Ubuntu: sudo apt install -y pandoc · macOS: brew install pandoc",
         "why": "every .docx/.pdf/.tex export of a paper, and importing a manuscript"},
        {"group": "export (export_to_path)", "what": "LibreOffice (soffice)", "ok": bool(req.get("soffice")),
         "programs": ("soffice", "libreoffice"), "needed": "recommended",
         "install": "Debian/Ubuntu: sudo apt install -y libreoffice-writer · macOS: brew install --cask libreoffice",
         "why": "recommended — normalises .docx so Hancom Office opens it; export works without it"},
        {"group": "presentations (/paper-deck)", "what": "LibreOffice (soffice)", "ok": bool(req.get("soffice")),
         "programs": ("soffice", "libreoffice"), "needed": "required",
         "install": "Debian/Ubuntu: sudo apt install -y libreoffice-impress · macOS: brew install --cask libreoffice",
         "why": "REQUIRED for any slide PNG/PDF — without it no preview renders at all"},
        {"group": "presentations (/paper-deck)", "what": "PyMuPDF (python module pymupdf)", "ok": bool(req.get("pymupdf")),
         "programs": (), "needed": "required",
         "install": f"{sys.executable} -m pip install pymupdf",
         "why": "PDF → PNG; a declared dependency — missing means pip ran with --no-deps"},
        {"group": "presentations (/paper-deck), Korean text anywhere", "what": "a Korean font (fonts-noto-cjk)",
         "ok": korean, "programs": ("fc-list",), "needed": "required",
         "install": "Debian/Ubuntu: sudo apt install -y fonts-noto-cjk · macOS: built in",
         "why": "without it Korean renders as boxes and the PNG still looks like a success"
                + ("" if korean is not None else
                   " — NOT CHECKED: `fc-list` (fontconfig) is not on PATH, so the installed fonts "
                   "could not be listed")},
        {"group": "study (preview_study)", "what": "a headless browser (Chrome or Chromium)",
         "ok": bool(find_browser()),
         "programs": tuple(b for b in _BROWSERS if not b.startswith("/")), "needed": "required",
         "install": "Debian/Ubuntu: sudo apt install -y chromium (or install Google Chrome) · "
                    "macOS: brew install --cask google-chrome",
         "why": "the only way a study page is seen before a person opens it; without it the "
                "preview is static checks only, and images, fonts and overflow go unmeasured"},
        {"group": "remote jobs (submit_remote_job)", "what": "ssh", "ok": bool(shutil.which("ssh")),
         "programs": ("ssh",), "needed": "required",
         "install": "Debian/Ubuntu: sudo apt install -y openssh-client · macOS: built in",
         "why": "every call to a registered server — launching, tailing a log, checking a pid"},
        {"group": "remote jobs (submit_remote_job)", "what": "rsync", "ok": bool(shutil.which("rsync")),
         "programs": ("rsync",), "needed": "recommended",
         "install": "Debian/Ubuntu: sudo apt install -y rsync · macOS: built in",
         "why": "copying a script or a result between this machine and a server"},
        {"group": "video (/video-*)", "what": "ffmpeg", "ok": bool(shutil.which("ffmpeg")),
         "programs": ("ffmpeg",), "needed": "required", "feature": "video",
         "install": "Debian/Ubuntu: sudo apt install -y ffmpeg · macOS: brew install ffmpeg",
         "why": "chunk joins, last-frame extraction, every video pipeline step"},
        {"group": "video (/video-*)", "what": "vh (python module)", "ok": _mod("vh"),
         "programs": (), "needed": "required", "feature": "video",
         "install": "git clone https://github.com/k821209/co-scientist-video-harness.git ~/co-scientist-video-harness && "
                    f"{sys.executable} -m pip install -e ~/co-scientist-video-harness",
         "why": "only if you make videos"},
    ]


def machine_report(*, video: bool = False) -> dict:
    """What this machine lacks, for a session rather than for a person at a
    terminal: `missing` (checked, not there), `unknown` (could not be
    checked), `checked` (how many rows were looked at). Video's rows count
    only where video is switched on — elsewhere "vh is missing" is true of
    every machine and tells nobody anything.

    Never raises: a report that cannot be made says so in `error`, with
    `missing` None, which is "not checked" and not "nothing missing".
    """
    try:
        rows = [r for r in checks() if r.get("feature") != "video" or video]
    except Exception as exc:  # noqa: BLE001 — the report must not break whoami
        return {"checked": 0, "missing": None, "unknown": None,
                "error": f"{type(exc).__name__}: {exc}"}

    def said(row: dict) -> dict:
        return {key: row[key] for key in ("what", "group", "needed", "why", "install")}

    return {
        "checked": len(rows),
        "missing": [said(r) for r in rows if r["ok"] is False],
        "unknown": [said(r) for r in rows if r["ok"] is None],
        "note": ("Programs a feature needs from this machine. An agent cannot install system "
                 "packages: before work that needs a missing one, tell the user what is missing, "
                 "what it stops, and the install line — do not start and fail, and do not swap "
                 "in another method without their yes."),
    }


def cli(argv: list[str]) -> int:
    rows = checks()
    print(f"scivo doctor — {sys.executable}")
    group = None
    missing = 0
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            print(f"\n  [{group}]")
        mark = "✓" if r["ok"] else ("?" if r["ok"] is None else "✗")
        print(f"    {mark} {r['what']}  — {r['why']}")
        if not r["ok"]:
            missing += r["ok"] is False
            print(f"        install: {r['install']}")
    print()
    if missing:
        print(f"  {missing} missing. Only the feature groups you use matter; an agent cannot "
              "install system packages for you.")
    else:
        print("  everything present.")
    return 1 if ("--strict" in argv and missing) else 0
