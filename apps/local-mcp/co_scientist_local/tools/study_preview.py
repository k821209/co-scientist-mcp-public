"""See a study the way the tab shows it — from the MCP side.

`/study-design` ended with "ask the user to look at the tab; you cannot see the
rendered page from here". That is a check the author is structurally unable
to run, left as an instruction to remember — the same shape as the cold-read
problem (feedback 9f22aae6c830, fourth point). This closes it where a browser
is available: the study's HTML is wrapped exactly as the dashboard wraps it
(the same packages/study_base.css, inside its layer, the theme attribute on
<html>, `asset:` images inlined from the project's own blobs), rendered by a
headless Chrome/Chromium on the user's machine, and the screenshot path is
returned for the agent to Read.

No browser → no screenshot, said plainly, plus the wrapped HTML file so a
person can open it. Never a silent "looks fine".
"""
from __future__ import annotations

import base64
import mimetypes
import os
import pathlib
import re
import shutil
import subprocess

from ..state import State

_PKG_DIR = pathlib.Path(__file__).resolve().parents[1]
_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
THEMES = ("light", "dark")


def find_study_base_css() -> pathlib.Path | None:
    bundled = _PKG_DIR / "study_base.css"          # wheel / pip-only install
    if bundled.is_file():
        return bundled
    repo = _PKG_DIR.parents[2] / "packages" / "study_base.css"   # editable / clone
    return repo if repo.is_file() else None


def study_base_css() -> str:
    f = find_study_base_css()
    return f.read_text(encoding="utf-8") if f else ""


def inject_study_base(html: str, *, dark: bool, css: str | None = None) -> str:
    """The dashboard's wrapping, mirrored (web/src/lib/studyDocument.ts
    injectStudyBase): base sheet at the top of <head>, theme on <html>, a
    fragment wrapped into a document."""
    css = study_base_css() if css is None else css
    theme = "dark" if dark else "light"
    style = f"<style data-scivo-base>{css}</style>"
    if re.search(r"<html[\s>]", html, re.I):
        def _html_tag(m: re.Match) -> str:
            attrs = m.group(1) or ""
            return m.group(0) if re.search(r"data-scivo-theme=", attrs, re.I) \
                else f'<html data-scivo-theme="{theme}"{attrs}>'
        out = re.sub(r"<html(\s[^>]*)?>", _html_tag, html, count=1, flags=re.I)
        if re.search(r"<head[\s>]", out, re.I):
            out = re.sub(r"(<head(?:\s[^>]*)?>)", lambda m: m.group(1) + style, out, count=1, flags=re.I)
        else:
            out = re.sub(r"(<html[^>]*>)", lambda m: m.group(1) + f"<head>{style}</head>", out, count=1, flags=re.I)
        return out
    return (f'<!doctype html><html data-scivo-theme="{theme}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'{style}</head><body>{html}</body></html>')


_ASSET_REF = re.compile(r'(\s(?:src|href)\s*=\s*)(["\'])asset:([A-Za-z0-9._-]+)\2')


def inline_assets(state: State, html: str) -> tuple[str, list[str]]:
    """`asset:NAME` → a data: URL from the project's own blob, as the tab
    would resolve it to a download URL. Unresolved names are left as written
    and listed, so a typo shows as a named missing image, not a blank."""
    missing: list[str] = []

    def repl(m: re.Match) -> str:
        name = m.group(3)
        doc = state.backend.get_doc(state.project_path("assets", name))
        blob = state.backend.get_blob(doc["blob_path"]) if doc and doc.get("blob_path") else None
        if not blob:
            missing.append(name)
            return m.group(0)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return f"{m.group(1)}{m.group(2)}data:{ctype};base64,{base64.b64encode(blob).decode()}{m.group(2)}"

    return _ASSET_REF.sub(repl, html), missing


def find_browser() -> str | None:
    for cand in _BROWSERS:
        p = shutil.which(cand) if not cand.startswith("/") else (cand if os.path.exists(cand) else None)
        if p:
            return p
    return None


def preview_study(
    state: State,
    study_id: str,
    *,
    theme: str = "light",
    width: int = 900,
    height: int = 1400,
    out_dir: str | None = None,
) -> dict:
    """Wrap the study as the tab does, screenshot it, return the file paths.

    `theme`: "light" | "dark" | "both". `height` is the viewport; the page is
    captured at that height, so a long study is seen from the top — enough
    to tell a wall of text from a typeset page, which is what this is for.
    """
    from . import studies as _studies
    doc = _studies.read_study(state, study_id)
    themes = THEMES if theme == "both" else ((theme,) if theme in THEMES else None)
    if themes is None:
        raise ValueError(f"theme must be one of light, dark, both — not {theme!r}")
    html, missing = inline_assets(state, doc.get("html") or "")
    base = pathlib.Path(out_dir or pathlib.Path.home() / ".co-scientist" / "cache" / "study-previews")
    base.mkdir(parents=True, exist_ok=True)
    browser = find_browser()
    out: dict = {"study_id": study_id, "title": doc.get("title"), "browser": browser,
                 "html": {}, "png": {}, "warnings": []}
    if missing:
        out["warnings"].append(f"asset(s) not found in this project, left unresolved: {', '.join(missing)}")
    if not doc.get("html", "").strip():
        out["warnings"].append("the study has no html")
    for th in themes:
        wrapped = inject_study_base(html, dark=(th == "dark"))
        html_path = base / f"{study_id}-{th}.html"
        html_path.write_text(wrapped, encoding="utf-8")
        out["html"][th] = str(html_path)
        if not browser:
            continue
        png_path = base / f"{study_id}-{th}.png"
        cmd = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
               f"--window-size={width},{height}", "--virtual-time-budget=4000",
               f"--screenshot={png_path}", html_path.as_uri()]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            out["warnings"].append(f"{th}: browser did not produce a screenshot ({e})")
            continue
        if r.returncode != 0 or not png_path.is_file():
            out["warnings"].append(f"{th}: browser exited {r.returncode}: {(r.stderr or '')[-200:]}")
            continue
        out["png"][th] = str(png_path)
    if not browser:
        out["warnings"].append(
            "no headless browser found (google-chrome / chromium on PATH) — no screenshot. "
            "The wrapped HTML above is exactly what the tab renders; open it, or ask the user "
            "to look at the tab. Do not report the page as checked.")
    out["next"] = ("Read the PNG(s) and look for: a wall of unstyled text, a table without rules, "
                   "a page that scrolls sideways, an image that did not load, dark-theme colours "
                   "that did not follow.") if out["png"] else None
    return out
