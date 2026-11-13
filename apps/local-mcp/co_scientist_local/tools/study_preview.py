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
import html as _html
import json
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


# What the browser is asked about the page, beside the picture of it. Named in
# the reply (`page_checks_run`) so "nothing found" can be told from "not
# looked for".
PAGE_CHECKS = ("images-loaded", "fonts-loaded", "sideways-overflow", "page-length")

# The frame's own page, around the study. The dashboard shows a study in a
# sandboxed frame that does not run its scripts until the reader switches them
# on (ProjectStudy.tsx); a bare page run by headless Chrome DID run them, so a
# study that builds its chart in a script previewed as a finished page and
# opened in the tab as an empty one. The frame here is sandboxed the same way.
# `allow-same-origin` is the one difference, and it is what lets the script
# BELOW — outside the frame, part of the preview and not of the study — read
# what the frame laid out: with scripts off inside, it changes nothing a study
# can do.
_FRAME_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;height:100%;background:#fff}
iframe{display:block;border:0;width:100vw;height:100vh}</style></head><body>
<iframe id="study" sandbox="allow-same-origin" srcdoc="__SRCDOC__"></iframe>
<script type="application/json" id="scivo-page">null</script>
<script>
(() => {
  const frame = document.getElementById('study');
  const say = (o) => { document.getElementById('scivo-page').textContent =
    JSON.stringify(o).replace(/</g, '\\u003c'); };
  const cut = (v) => String(v || '').slice(0, 90);
  const measure = () => {
    const d = frame.contentDocument, root = d.documentElement;
    const images = [...d.images];
    const failed = images.filter((i) => !(i.complete && i.naturalWidth > 0))
      .map((i) => ({ src: cut(i.getAttribute('src')), alt: cut(i.getAttribute('alt')) }));
    const fonts = [...(d.fonts || [])].filter((f) => f.status === 'error').map((f) => cut(f.family));
    const view = frame.clientWidth;
    let widest = null, edge = view + 1;
    for (const n of [...d.body.querySelectorAll('*')].slice(0, 4000)) {
      const r = n.getBoundingClientRect();
      if (r.width && r.right > edge) {
        edge = r.right;
        widest = n.tagName.toLowerCase() + (n.id ? '#' + n.id : '')
          + (typeof n.className === 'string' && n.className.trim()
             ? '.' + n.className.trim().split(/\\s+/).join('.') : '');
      }
    }
    say({ images: images.length, images_failed: failed, fonts_failed: fonts,
          scripts: d.scripts.length, view_width: view, view_height: frame.clientHeight,
          page_width: root.scrollWidth, page_height: root.scrollHeight, widest: cut(widest) });
  };
  let tries = 0;
  const wait = () => {
    const d = frame.contentDocument;
    if (d && d.readyState === 'complete' && d.body && (d.body.childNodes.length || tries > 20)) {
      (d.fonts ? d.fonts.ready : Promise.resolve()).then(measure, measure);
    } else if (tries++ < 60) setTimeout(wait, 50);
    else say({ error: 'the frame never finished loading' });
  };
  wait();
})();
</script></body></html>"""

_PAGE_JSON = re.compile(r'<script type="application/json" id="scivo-page">(.*?)</script>', re.S)


def frame_page(wrapped: str) -> str:
    """The study inside the frame the tab gives it, plus the page checks."""
    return _FRAME_PAGE.replace("__SRCDOC__", _html.escape(wrapped, quote=True))


def read_page_checks(dom: str) -> dict | None:
    """What the frame page measured, out of a `--dump-dom`. None when it said
    nothing — which is "not checked", never "nothing wrong"."""
    m = _PAGE_JSON.search(dom or "")
    if not m:
        return None
    try:
        page = json.loads(_html.unescape(m.group(1)))
    except ValueError:
        return None
    return page if isinstance(page, dict) and "error" not in page else None


def page_warnings(page: dict, *, height: int) -> list[str]:
    """Sentences for what the measurements show. Each of these was "look for
    it in the PNG" before, and two of them cannot be seen in the PNG at all: a
    broken image with alt text draws as a line of small text, and sideways
    overflow is cut off at the window edge with the scrollbar hidden."""
    out: list[str] = []
    failed = page.get("images_failed") or []
    if failed:
        named = "; ".join((f.get("alt") or "(no alt)") + " ← " + (f.get("src") or "(no src)")
                          for f in failed[:6])
        out.append(f"{len(failed)} of {page.get('images')} image(s) did not load: {named}"
                   + (" …" if len(failed) > 6 else ""))
    if page.get("fonts_failed"):
        out.append("font(s) failed to load, so the text is in a fallback face: "
                   + ", ".join(sorted(set(page["fonts_failed"]))[:6]))
    wide, view = page.get("page_width") or 0, page.get("view_width") or 0
    if view and wide > view + 1:
        out.append(f"the page scrolls sideways: {wide} px of content in a {view} px frame"
                   + (f" — the widest element is `{page['widest']}`" if page.get("widest") else ""))
    tall = page.get("page_height") or 0
    if tall > height + 1:
        out.append(f"the screenshot shows the top {height} of {tall} px "
                   f"({round(100 * height / tall)}% of the page) — the rest was not looked at; "
                   f"call again with height={min(tall, MAX_HEIGHT)} to see "
                   + ("all of it" if tall <= MAX_HEIGHT else f"the first {MAX_HEIGHT} px"))
    if page.get("scripts"):
        out.append(f"the study has {page['scripts']} <script> element(s). The tab does not run "
                   "scripts until the reader switches them on, and this preview shows the page "
                   "that way — anything a script draws is missing from both")
    return out


MAX_HEIGHT = 16000


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
    captured at that height, so a long study is seen from the top — and the
    reply says how much of the page that was. `page` carries what the browser
    measured (`PAGE_CHECKS`): images and fonts that did not load, sideways
    overflow, the page's full length.
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
                 "html": {}, "png": {}, "warnings": [], "page": None,
                 "page_checks_run": []}
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
        # The browser is pointed at the FRAME page, not at the study: the
        # study file above stays what a person opens.
        frame_path = base / f"{study_id}-{th}.frame.html"
        frame_path.write_text(frame_page(wrapped), encoding="utf-8")
        png_path = base / f"{study_id}-{th}.png"
        png_path.unlink(missing_ok=True)     # never report the last run's picture
        common = [browser, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
                  f"--window-size={width},{height}", "--virtual-time-budget=4000"]
        try:
            r = subprocess.run([*common, f"--screenshot={png_path}", frame_path.as_uri()],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            out["warnings"].append(f"{th}: browser did not produce a screenshot ({e})")
            continue
        if r.returncode != 0 or not png_path.is_file():
            out["warnings"].append(f"{th}: browser exited {r.returncode}: {(r.stderr or '')[-200:]}")
            continue
        out["png"][th] = str(png_path)
        if out["page"] is None:
            # Once, on the first theme that rendered: what loads and how wide
            # the page is do not depend on the theme.
            try:
                d = subprocess.run([*common, "--dump-dom", frame_path.as_uri()],
                                   capture_output=True, text=True, timeout=60)
                out["page"] = read_page_checks(d.stdout)
            except (OSError, subprocess.TimeoutExpired):
                out["page"] = None
    if out["page"] is not None:
        out["page_checks_run"] = list(PAGE_CHECKS)
        out["warnings"].extend(page_warnings(out["page"], height=height))
    elif out["png"]:
        # A picture with no measurements: say so, or an absent warning reads
        # as "every image loaded".
        out["warnings"].append(
            "the page checks did not come back (" + ", ".join(PAGE_CHECKS) + ") — the "
            "screenshot exists, but whether every image and font loaded and whether the "
            "page overflows sideways was NOT measured; look for them in the PNG")
    # Static checks run with or without a browser: the breakages a parser
    # makes (a CDATA wrapper, an unclosed <style>) are findable without one,
    # and on a machine with no browser they were the only thing that would
    # have caught a stylesheet printed as page text (feedback 160481377be0).
    from .studies import STATIC_CHECKS, static_checks
    out["static_problems"] = static_checks(html)
    # WHAT was looked for, beside what was found. An empty `static_problems`
    # read as "nothing found" while the checks were blind to the whole class of
    # defect that makes a page fail to render — and nothing in the reply let
    # the two be told apart (feedback de487cc198d4).
    out["static_checks_run"] = list(STATIC_CHECKS)
    for p in out["static_problems"]:
        out["warnings"].append(f"static check: {p}")
    if not browser:
        out["warnings"].append(
            "no headless browser found (google-chrome / chromium on PATH) — no screenshot. "
            f"The {len(STATIC_CHECKS)} static checks in `static_checks_run` ran and are all "
            "that ran: they find a parser-level breakage and two kinds of inert CSS, NOT "
            "whether the layout reads. The wrapped HTML is exactly what the tab renders — "
            "open it, or ask the user to look at the tab. Do not report the page as checked.")
    out["next"] = ("Read the PNG(s) and look for what cannot be measured: a wall of unstyled "
                   "text, a table without rules, dark-theme colours that did not follow. Images "
                   "and fonts that did not load, sideways overflow and how much of the page the "
                   "screenshot covers are in `warnings`, measured — when `page_checks_run` is "
                   "empty they were not, and are yours to look for.") if out["png"] else None
    return out
