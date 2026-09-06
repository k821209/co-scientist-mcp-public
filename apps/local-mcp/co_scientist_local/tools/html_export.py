"""Single-file HTML export: the stylesheet, the optional course-mode script,
and the pandoc arguments that tie them together.

Why a format of its own and not "just pandoc -t html": the request that
produced this (feedback 18da3e6dbcd1) was a training document that had to
travel as ONE file — opened from a USB stick, a chat attachment, a phone — with
no CDN, no sidecar image folder, and readable with scripts disabled. Pandoc
gives the skeleton (`--standalone --embed-resources`, which inlines the
stylesheet, the script and every figure as data: URIs); what it does not give
is a document someone would want to read, which is the stylesheet, and the
handful of course-room affordances, which is the script.

Two themes:

  paper   — a reading page: measured line length, serif body, captioned
            figures, tables that scroll sideways on a phone instead of
            breaking the layout, a print stylesheet. No script at all.
  course  — the paper theme plus: a table of contents that stays at the side
            on a wide screen, a "copy" button on every code block, a
            language badge on fenced code (```bash → LINUX, ```powershell →
            POWERSHELL — pure CSS, driven by the fence's class), task-list
            checkboxes the reader can tick (remembered in the browser), and
            styled <details> for fold-away solutions. Everything the script
            adds is an addition: with JavaScript off the page is the paper
            theme with a top-of-page contents list.

Nothing here is a template: pandoc's own HTML5 template is used, so headings,
footnotes, citations and math (as MathML, which needs no script) all come out
as pandoc makes them.
"""
from __future__ import annotations

import pathlib

VALID_THEMES = ("paper", "course")

# pandoc ≥ 2.19 spells it --embed-resources; older ones only know
# --self-contained. The export tries the new flag and falls back.
EMBED_FLAG = "--embed-resources"
EMBED_FLAG_LEGACY = "--self-contained"

STYLE_FILENAME = "style.css"
HEAD_FILENAME = "head.html"

_BASE_CSS = """\
:root {
  --fg: #1c1c1e; --muted: #5f6368; --bg: #ffffff; --panel: #f6f7f9;
  --line: #e1e4e8; --accent: #0b5fff; --code-bg: #f4f5f7;
}
@media (prefers-color-scheme: dark) {
  :root { --fg: #e8e8ea; --muted: #a0a4ab; --bg: #121315; --panel: #1b1d21;
          --line: #2c3037; --accent: #6ea8ff; --code-bg: #1b1d21; }
}
html { color-scheme: light dark; }
body {
  max-width: 46rem; margin: 0 auto; padding: 0 1.25rem 4rem; background: var(--bg); color: var(--fg);
  font-family: Georgia, "Noto Serif KR", "Apple SD Gothic Neo", "Malgun Gothic", serif;
  font-size: 1.05rem; line-height: 1.65; -webkit-text-size-adjust: 100%;
}
h1, h2, h3, h4 { line-height: 1.25; font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; }
h1 { font-size: 1.9rem; margin-top: 2rem; }
h2 { font-size: 1.45rem; margin-top: 2.2rem; border-bottom: 1px solid var(--line); padding-bottom: .25rem; }
h3 { font-size: 1.15rem; margin-top: 1.6rem; }
a { color: var(--accent); }
p { margin: .8rem 0; }
img { max-width: 100%; height: auto; }
figure { margin: 1.5rem 0; text-align: center; }
figcaption { font-size: .9rem; color: var(--muted); margin-top: .4rem; text-align: left; }
table { border-collapse: collapse; margin: 1.2rem 0; font-size: .92rem;
        display: block; max-width: 100%; overflow-x: auto; }
th, td { border: 1px solid var(--line); padding: .35rem .6rem; text-align: left; vertical-align: top; }
th { background: var(--panel); }
caption { caption-side: top; text-align: left; font-weight: 600; margin-bottom: .3rem; }
pre { background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px;
      padding: .75rem .9rem; overflow-x: auto; font-size: .88rem; line-height: 1.5; }
code { font-family: ui-monospace, "SFMono-Regular", Menlo, Consolas, "Noto Sans Mono CJK KR", monospace; }
p code, li code, td code { background: var(--code-bg); padding: .1rem .3rem; border-radius: 4px; font-size: .9em; }
blockquote { margin: 1rem 0; padding: .2rem 1rem; border-left: 3px solid var(--line); color: var(--muted); }
hr { border: 0; border-top: 1px solid var(--line); margin: 2rem 0; }
nav#TOC { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
          padding: .75rem 1rem; margin: 1.5rem auto; font-size: .92rem;
          font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans KR", sans-serif; }
nav#TOC ul { padding-left: 1.1rem; margin: .2rem 0; }
nav#TOC > ul { padding-left: 0; list-style: none; }
nav#TOC a { text-decoration: none; }
.footnotes { font-size: .9rem; color: var(--muted); }
@media print {
  body { padding: 0; font-size: 11pt; color: #000; background: #fff; }
  nav#TOC, .cs-copy { display: none !important; }
  a { color: inherit; text-decoration: none; }
  pre, figure, table { break-inside: avoid; }
  h2, h3 { break-after: avoid; }
}
"""

_COURSE_CSS = """\
/* course: sans body, side contents on wide screens, code affordances */
body { font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans KR", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; }
@media (min-width: 72rem) {
  body { margin-left: 19rem; margin-right: auto; }
  nav#TOC { position: fixed; top: 0; left: 0; bottom: 0; width: 16rem; margin: 0;
            border-radius: 0; border-width: 0 1px 0 0; overflow-y: auto; padding: 1rem; }
  nav#TOC a.cs-current { font-weight: 600; color: var(--fg); }
}
div.sourceCode { position: relative; }
pre.sourceCode::before {
  content: attr(data-lang); position: absolute; top: .45rem; right: 4.2rem;
  font: 600 .68rem/1 system-ui, sans-serif; letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); pointer-events: none;
}
pre.bash::before, pre.sh::before, pre.shell::before, pre.console::before { content: "Linux"; }
pre.powershell::before, pre.ps1::before { content: "PowerShell"; }
pre.cmd::before, pre.bat::before { content: "CMD"; }
pre.python::before { content: "Python"; }
pre.r::before { content: "R"; }
button.cs-copy {
  position: absolute; top: .3rem; right: .5rem; font: .72rem system-ui, sans-serif;
  padding: .15rem .45rem; border: 1px solid var(--line); border-radius: 4px;
  background: var(--bg); color: var(--muted); cursor: pointer; opacity: .75;
}
button.cs-copy:hover, button.cs-copy:focus { opacity: 1; color: var(--fg); }
details { border: 1px solid var(--line); border-radius: 6px; padding: .5rem .9rem; margin: 1rem 0; background: var(--panel); }
details > summary { cursor: pointer; font-weight: 600; }
details[open] > summary { margin-bottom: .5rem; }
ul.task-list { list-style: none; padding-left: .25rem; }
ul.task-list li { margin: .35rem 0; }
ul.task-list li input[type=checkbox] { width: 1.05rem; height: 1.05rem; margin: 0 .5rem 0 0; vertical-align: -.15rem; }
ul.task-list li.cs-done { color: var(--muted); text-decoration: line-through; }
"""

# Everything the script does is optional: without it the page is still the
# whole document, with the contents list at the top and untickable boxes.
_COURSE_JS = """\
<script>
(function () {
  if (!document.addEventListener) return;
  document.addEventListener("DOMContentLoaded", function () {
    // 1. copy button on every code block
    var blocks = document.querySelectorAll("div.sourceCode");
    for (var i = 0; i < blocks.length; i++) (function (block) {
      var pre = block.querySelector("pre");
      if (!pre || !navigator.clipboard) return;
      var b = document.createElement("button");
      b.type = "button"; b.className = "cs-copy"; b.textContent = "copy";
      b.setAttribute("aria-label", "copy code");
      b.addEventListener("click", function () {
        navigator.clipboard.writeText(pre.innerText.replace(/\\n$/, "")).then(function () {
          b.textContent = "copied"; setTimeout(function () { b.textContent = "copy"; }, 1200);
        });
      });
      block.appendChild(b);
    })(blocks[i]);
    // 2. task-list boxes the reader can tick; remembered per page in this browser
    var key = "cs-tasks:" + location.pathname + ":" + (document.title || "");
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(key) || "{}"); } catch (e) {}
    var boxes = document.querySelectorAll("ul.task-list input[type=checkbox]");
    for (var j = 0; j < boxes.length; j++) (function (box, idx) {
      box.disabled = false;
      if (saved[idx] != null) box.checked = !!saved[idx];
      var li = box.closest ? box.closest("li") : null;
      var paint = function () { if (li) li.classList.toggle("cs-done", box.checked); };
      paint();
      box.addEventListener("change", function () {
        saved[idx] = box.checked; paint();
        try { localStorage.setItem(key, JSON.stringify(saved)); } catch (e) {}
      });
    })(boxes[j], j);
    // 3. current section in the side contents
    var links = document.querySelectorAll("nav#TOC a[href^='#']");
    if (!links.length || !("IntersectionObserver" in window)) return;
    var byId = {};
    for (var k = 0; k < links.length; k++) byId[decodeURIComponent(links[k].getAttribute("href").slice(1))] = links[k];
    var obs = new IntersectionObserver(function (entries) {
      for (var e = 0; e < entries.length; e++) if (entries[e].isIntersecting) {
        for (var k2 = 0; k2 < links.length; k2++) links[k2].classList.remove("cs-current");
        var a = byId[entries[e].target.id]; if (a) a.classList.add("cs-current");
      }
    }, { rootMargin: "0px 0px -70% 0px" });
    for (var id in byId) { var el = document.getElementById(id); if (el) obs.observe(el); }
  });
})();
</script>
"""


def validate_theme(theme: str | None) -> str:
    theme = (theme or "paper").lower()
    if theme not in VALID_THEMES:
        raise ValueError(f"invalid theme {theme!r}; choose from {VALID_THEMES}")
    return theme


def stylesheet(theme: str) -> str:
    return _BASE_CSS + (_COURSE_CSS if theme == "course" else "")


def head_html(theme: str) -> str:
    """Inline <head> additions. A viewport meta for every theme (pandoc's
    template has one already, harmless twice); the script only for course."""
    return _COURSE_JS if theme == "course" else ""


def write_theme_files(tmp_path: pathlib.Path, theme: str) -> None:
    (tmp_path / STYLE_FILENAME).write_text(stylesheet(theme), encoding="utf-8")
    (tmp_path / HEAD_FILENAME).write_text(head_html(theme), encoding="utf-8")


def pandoc_args(*, title: str | None, embed_flag: str = EMBED_FLAG) -> list[str]:
    """The html-specific pandoc arguments (appended to the common ones).

    `--mathml` rather than MathJax: no script and no network for formulas.
    (pandoc 3 prints a deprecation note and honours it; the replacement
    spelling, `--math-method=mathml`, does not exist in pandoc 2.)
    `pagetitle`, not `title`: the manuscript already carries its own heading
    and pandoc's title block would print it twice.
    """
    args = [
        "-t", "html5", "--standalone", embed_flag,
        "--toc", "--toc-depth=3", "--mathml",
        "--css", STYLE_FILENAME,
        "--include-in-header", HEAD_FILENAME,
    ]
    if title:
        args.extend(["--metadata", f"pagetitle={title}"])
    return args
