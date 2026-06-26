"""Manuscript export: prepare bundle, run pandoc, upload result to Storage.

`prepare_export` is pure data — collects everything pandoc will need:
- assembled manuscript text (from compile_manuscript)
- references converted to BibTeX
- figures with their blob paths
- warnings: placeholder markers (TBD/TK/XXX/TODO) and unresolved `{doi:…}`
  citations not present in any reference's `doi` field.

`export_to_path` runs the full pipeline:
1. prepare_export
2. Lay out a temp dir: manuscript.md, references.bib, figure files
3. Invoke pandoc to produce the output file
4. Upload the output to Cloud Storage at
   `users/{uid}/papers/{slug}/exports/{filename}` so the dashboard can serve it.
"""
from __future__ import annotations

import json
import io
import pathlib
import re
import shutil
import subprocess
import tempfile
import zipfile

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso
from . import csl as _csl
from . import docx_export as _docx_export
from . import figures as _figures
from . import papers as _papers
from . import references as _references
from . import requirements as _requirements
from . import reviews as _reviews
from . import sections as _sections
from . import tables as _tables


_DOI_INLINE_RE = re.compile(r"\{doi:([^}]+)\}")
# A run of adjacent {doi:…} markers (optionally whitespace-separated), so a
# stacked citation collapses into a single pandoc group instead of [@a][@b].
_DOI_RUN_RE = re.compile(r"\{doi:[^}]+\}(?:\s*\{doi:[^}]+\})*")
_PLACEHOLDER_RE = re.compile(r"\b(TBD|TK|XXX|TODO|FIXME)\b", re.IGNORECASE)
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[(?:\.{3}|placeholder|tbd|tk|xxx|todo|fixme)\]", re.IGNORECASE)


def _scan_placeholders(text: str) -> list[dict]:
    """Find TODO-like markers per line. Returns [{line, snippet, marker}]."""
    out: list[dict] = []
    for i, line in enumerate(text.splitlines(), start=1):
        for m in _PLACEHOLDER_RE.finditer(line):
            out.append({"line": i, "marker": m.group(0).upper(),
                        "snippet": line.strip()[:200]})
        for m in _BRACKET_PLACEHOLDER_RE.finditer(line):
            out.append({"line": i, "marker": m.group(0),
                        "snippet": line.strip()[:200]})
    return out


def _extract_cited_dois(text: str) -> list[str]:
    return _DOI_INLINE_RE.findall(text)


_THEMATIC_BREAK_RE = re.compile(r"(?m)^[ \t]*-{3,}[ \t]*$")


def _escape_thematic_breaks(text: str) -> str:
    """Disambiguate '---' rules for pandoc (dev-todo P1-3). The YAML metadata
    fence is already turned off via `-f markdown-yaml_metadata_block`, but a
    '---' line directly under a paragraph is still read as a setext-H2
    underline (silently promoting that text to a heading). Rewriting standalone
    dash rules to '***' keeps the intended thematic break with no ambiguity.
    """
    return _THEMATIC_BREAK_RE.sub("***", text)


_INLINE_FIGURE_RE = re.compile(r"!\[([^\]]*)\]\(figure:(\d+)\)")


def _rewrite_inline_figure_refs(
    text: str, figures: list[dict], supp_figures: list[dict]
) -> str:
    """Rewrite body embeds `![alt](figure:N)` to point at the staged image file
    (`figure_N.png`) that export_to_path writes into pandoc's working dir.

    The web renderer resolves the `figure:N` scheme to the figure's download
    URL; pandoc can't, so without this rewrite it looks for a file literally
    named `figure:N` and emits a broken/missing image. An unresolved N (no
    blob) drops the image node and keeps the alt text as plain caption text.
    """
    name_by_num: dict[int, str] = {}
    for fig in (*figures, *supp_figures):
        bp = fig.get("blob_path")
        num = fig.get("figure_number")
        if bp and isinstance(num, int):
            name_by_num[num] = pathlib.Path(bp).name

    def repl(m: re.Match) -> str:
        alt, num = m.group(1), int(m.group(2))
        name = name_by_num.get(num)
        return f"![{alt}]({name})" if name else alt

    return _INLINE_FIGURE_RE.sub(repl, text)


def _rewrite_inline_citations(
    text: str, refs: list[dict]
) -> tuple[str, list[str]]:
    """Rewrite body `{doi:DOI}` markers to pandoc citations `[@citation_key]`.

    Without this, --citeproc never sees a citation: the literal `{doi:…}`
    string passes straight through into the .docx and no bibliography is
    emitted (the web renderer turns the marker into a link, so the gap only
    surfaces on export). Matching is case-insensitive on the DOI — refs from
    CrossRef are stored lowercased, but a manually-added DOI may not be, and
    the body marker may use either case.

    DOIs with no registered reference are left literal and returned so the
    caller can warn; they're the same set prepare_export already reports as
    `unresolved_citations`.

    A RUN of adjacent markers `{doi:A}{doi:B}` must collapse into ONE pandoc
    citation group `[@a; @b]`, not `[@a][@b]` — pandoc parses `[@a][@b]` as a
    markdown link `[text](target)` and mangles the output (the canonical body
    form is adjacent tokens, so this hits every stacked citation).
    """
    key_by_doi = {
        (r.get("doi") or "").strip().lower(): r["citation_key"]
        for r in refs
        if r.get("doi") and r.get("citation_key")
    }
    unmatched: list[str] = []

    def repl(m: re.Match) -> str:
        keys: list[str] = []
        leftover: list[str] = []
        for doi in _DOI_INLINE_RE.findall(m.group(0)):
            d = doi.strip()
            key = key_by_doi.get(d.lower())
            if key:
                keys.append(key)
            else:
                unmatched.append(d)
                leftover.append("{doi:%s}" % doi)
        cite = "[%s]" % "; ".join("@" + k for k in keys) if keys else ""
        return cite + "".join(leftover)

    return _DOI_RUN_RE.sub(repl, text), unmatched


def _figures_appendix(
    figures: list[dict], supp_figures: list[dict], heading: str = "Figures"
) -> str:
    """Markdown that embeds each registered figure's image as a Pandoc figure.

    The body only carries 'Figure N' text references, so without this pandoc
    has no image to embed (dev-todo EXP-1). We append a Figures section whose
    image targets are the blob basenames — matching the files export_to_path
    writes into the pandoc working dir.
    """
    def block(fig: dict, supplementary: bool) -> str | None:
        bp = fig.get("blob_path")
        if not bp:
            return None
        local_name = pathlib.Path(bp).name
        num = fig.get("figure_number")
        if supplementary and isinstance(num, int):
            label = f"Figure S{num - _figures.SUPPLEMENTARY_NUMBER_OFFSET}"
        else:
            label = f"Figure {num}"
        parts = [label.rstrip(".") + "."]
        for field in ("caption", "legend"):
            val = (fig.get(field) or "").strip()
            if val:
                parts.append(val)
        # Alt text becomes the docx/PDF caption; collapse newlines so the
        # `![ ... ]( ... )` stays a single image node.
        alt = " ".join(parts).replace("\n", " ").strip()
        return f"![{alt}]({local_name})"

    blocks = [b for b in (
        *(block(f, False) for f in figures),
        *(block(f, True) for f in supp_figures),
    ) if b]
    if not blocks:
        return ""
    return f"## {heading}\n\n" + "\n\n".join(blocks) + "\n"


def _tables_appendix(
    tables: list[dict], supp_tables: list[dict], heading: str = "Tables"
) -> str:
    """Markdown that appends each registered table after the body.

    Like figures, the body only carries 'Table N' text references — the table
    markup itself lives in each table doc's `content` (a pandoc/GFM pipe table)
    and was never concatenated into the manuscript, so pandoc/python-docx never
    saw it and every export dropped all tables (dev-todo: tables-appendix). We
    emit a Tables section: a bold 'Table N.' caption line followed by the
    stored pipe-table markdown, mirroring `_figures_appendix`.
    """
    def block(tbl: dict, supplementary: bool) -> str | None:
        content = (tbl.get("content") or "").strip()
        if not content:
            return None
        num = tbl.get("table_number")
        if supplementary and isinstance(num, int):
            label = f"Table S{num - _figures.SUPPLEMENTARY_NUMBER_OFFSET}"
        else:
            label = f"Table {num}"
        caption = (tbl.get("caption") or tbl.get("title") or "").strip()
        caption = " ".join(caption.split())  # collapse newlines for the caption line
        head = f"**{label}.** {caption}".rstrip() if caption else f"**{label}.**"
        # Blank line between the caption and the table so it parses as a block.
        return f"{head}\n\n{content}"

    blocks = [b for b in (
        *(block(t, False) for t in tables),
        *(block(t, True) for t in supp_tables),
    ) if b]
    if not blocks:
        return ""
    return f"## {heading}\n\n" + "\n\n".join(blocks) + "\n"


def _ref_to_bibtex(ref: dict) -> str:
    """Build a minimal @article BibTeX entry from a reference doc.

    If the ref carries a literal `bibtex` field, return that verbatim.
    """
    if ref.get("bibtex"):
        return ref["bibtex"].rstrip() + "\n"
    key = ref.get("citation_key") or "unknown"
    fields: list[str] = []
    if ref.get("title"):
        fields.append(f"  title = {{{ref['title']}}}")
    authors = ref.get("authors")
    if isinstance(authors, list):
        author_str = " and ".join(authors)
    else:
        author_str = authors
    if author_str:
        fields.append(f"  author = {{{author_str}}}")
    if ref.get("journal"):
        fields.append(f"  journal = {{{ref['journal']}}}")
    if ref.get("year"):
        fields.append(f"  year = {{{ref['year']}}}")
    if ref.get("doi"):
        fields.append(f"  doi = {{{ref['doi']}}}")
    body = ",\n".join(fields)
    return f"@article{{{key},\n{body}\n}}\n"


def prepare_export(state: State, slug: str) -> dict:
    """Collect everything needed to export `slug` to a finished document.

    Returns a dict with:
        slug, paper, sections, manuscript (str), figures, tables,
        references, bibtex (str), warnings, placeholders,
        unresolved_citations (list of DOIs), suggested_csl_filename.
    """
    bundle = _papers.get_paper_state(state, slug)
    figs = _figures.list_figures(state, slug)
    supp_figs = _figures.list_figures(state, slug, supplementary=True)
    tbls = _tables.list_tables(state, slug)
    supp_tbls = _tables.list_tables(state, slug, supplementary=True)
    refs = _references.list_references(state, slug)

    manuscript = bundle["manuscript"]
    placeholders = _scan_placeholders(manuscript)
    cited_dois = _extract_cited_dois(manuscript)
    known_dois = {r["doi"] for r in refs if r.get("doi")}
    unresolved = sorted(set(cited_dois) - known_dois)

    bibtex = "".join(_ref_to_bibtex(r) for r in refs)

    paper = bundle["paper"]
    # Resolve the journal's citation style (offline — registry → in-code map →
    # kebab guess). export_to_path does the actual download.
    csl = _csl.resolve_csl_filename(state, paper.get("journal"))

    # Journal / paper-type requirement check (word limits, item caps, …).
    req_check = _requirements.check_requirements(state, slug)

    # Review-triage gate: accepted comments must be resolved, and rejected
    # comments must carry a rebuttal (response) for the response letter.
    triage = _reviews.review_triage_summary(state, slug)

    warnings: list[str] = []
    if placeholders:
        warnings.append(f"{len(placeholders)} placeholder marker(s) in manuscript")
    if unresolved:
        warnings.append(f"{len(unresolved)} unresolved {{doi:…}} citation(s)")
    for s in bundle["sections"]:
        if s.get("status") == "pending" and (s.get("word_count") or 0) == 0:
            warnings.append(f"section '{s['key']}' is empty")
    if req_check.get("violations"):
        warnings.append(
            f"{len(req_check['violations'])} journal-requirement violation(s) "
            f"— see requirements_check"
        )
    if triage["rejected_without_rationale"]:
        warnings.append(
            f"{triage['rejected_without_rationale']} rejected comment(s) missing a "
            f"rebuttal (response) — see review_triage / run /paper-revision"
        )
    if triage["accepted_unresolved"]:
        warnings.append(
            f"{triage['accepted_unresolved']} accepted comment(s) not yet resolved "
            f"— see review_triage"
        )

    return {
        "slug": slug,
        "paper": paper,
        "sections": bundle["sections"],
        "manuscript": manuscript,
        "figures": figs,
        "supplementary_figures": supp_figs,
        "tables": tbls,
        "supplementary_tables": supp_tbls,
        "references": refs,
        "bibtex": bibtex,
        "placeholders": placeholders,
        "unresolved_citations": unresolved,
        "csl_filename": csl["csl_filename"],
        "csl_slug": csl["csl_slug"],
        "csl_source": csl["csl_source"],
        "csl_status": csl["csl_status"],
        "requirements_check": req_check,
        "review_triage": triage,
        "warnings": warnings,
    }


_VALID_FORMATS = {"docx", "tex", "pdf", "md"}


def _format_pandoc_args(fmt: str, manuscript_filename: str, output_filename: str,
                       has_bib: bool, csl_path: str | None) -> list[str]:
    # Disable yaml_metadata_block so a body-level `---` (thematic break /
    # section divider) isn't mis-parsed as YAML front matter and crash the
    # export (dev-todo P1-3). Everything else in pandoc's markdown stays on.
    args: list[str] = [
        manuscript_filename,
        "-f", "markdown-yaml_metadata_block",
        "-o", output_filename,
    ]
    if fmt == "tex":
        args.extend(["-t", "latex"])
    elif fmt == "pdf":
        # Use default pdf engine (xelatex/pdflatex if available)
        pass
    elif fmt == "md":
        args.extend(["-t", "markdown"])
    # docx is the implicit default when output ext is .docx
    if has_bib:
        args.extend(["--bibliography", "references.bib", "--citeproc"])
    if csl_path:
        args.extend(["--csl", csl_path])
    return args


def _place_csl(
    state: State,
    tmp_path: pathlib.Path,
    bundle: dict,
    explicit_csl_path: str | None,
) -> tuple[str | None, str, str | None, list[str]]:
    """Put a CSL style file into `tmp_path` for pandoc to use.

    Returns (csl_arg, csl_status, csl_filename, warnings):
      - csl_arg      — filename to pass to `pandoc --csl`, or None
      - csl_status   — explicit | downloaded | missing | no_journal
      - csl_filename — the resolved/used filename, or None
      - warnings     — human-readable notes for the export report

    An explicit path wins. Otherwise the journal (already resolved to a
    filename by prepare_export) is downloaded from the CSL styles repo; a
    successful download of a *guessed* slug is written back to the
    per-project registry so it sticks.
    """
    warnings: list[str] = []

    if explicit_csl_path:
        src = pathlib.Path(explicit_csl_path).expanduser()
        if src.is_file():
            shutil.copy2(src, tmp_path / src.name)
            return src.name, "explicit", src.name, warnings
        warnings.append(
            f"csl_path not found: {explicit_csl_path} — used pandoc's "
            "default citation style"
        )
        return None, "missing", None, warnings

    csl_filename = bundle.get("csl_filename")
    if not csl_filename:
        return None, "no_journal", None, warnings

    try:
        data = _csl.download_csl(csl_filename)
    except _csl.CslNotFound as e:
        warnings.append(
            f"CSL '{csl_filename}' not in the styles repo ({e}) — used "
            "pandoc's default citation style. If you know the correct "
            "filename, register it with register_journal_csl."
        )
        return None, "missing", csl_filename, warnings
    except Exception as e:  # network failure — non-fatal, fall back
        warnings.append(
            f"CSL download failed ({e}) — used pandoc's default style"
        )
        return None, "missing", csl_filename, warnings

    (tmp_path / csl_filename).write_bytes(data)
    # Cache a working guess so the next export of this journal skips guessing.
    if bundle.get("csl_source") == "guess":
        try:
            _csl.register_journal_csl(
                state, bundle["paper"].get("journal") or "", csl_filename,
                notes="auto-registered after a successful CSL download",
            )
        except Exception:
            pass
    return csl_filename, "downloaded", csl_filename, warnings


# pandoc emits several near-empty OOXML parts (comments.xml, docProps/
# custom.xml, ...). Word/LibreOffice/Google Docs tolerate them, but Hancom
# Office's OOXML importer SIGSEGVs (dev-todo P0-1). The robust fix is a
# LibreOffice round-trip (`_normalize_docx_via_soffice`); when soffice is
# unavailable we fall back to stripping the known-problem parts + their refs.
_DOCX_PROBLEM_PARTS = (
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
    "docProps/custom.xml",
)


def _normalize_docx_via_soffice(path: pathlib.Path) -> bool:
    """Round-trip the .docx through LibreOffice in place to normalize its
    OOXML into a structure Hancom Office can open. soffice rewrites the whole
    package cleanly, dropping the empty parts that crash Hancom's importer —
    more robust than chasing individual parts. Returns True if the file was
    replaced; False if soffice/libreoffice is missing or conversion failed.
    """
    for binary in ("soffice", "libreoffice"):
        with tempfile.TemporaryDirectory(prefix="docx-norm-") as d:
            try:
                proc = subprocess.run(
                    [binary, "--headless", "--convert-to", "docx",
                     "--outdir", d, str(path)],
                    capture_output=True, text=True, timeout=180,
                )
            except FileNotFoundError:
                continue  # try the next binary name
            except subprocess.TimeoutExpired:
                return False
            produced = pathlib.Path(d) / f"{path.stem}.docx"
            if proc.returncode == 0 and produced.is_file():
                shutil.copy2(produced, path)
                return True
            return False
    return False


def _strip_problem_docx_parts(path: pathlib.Path) -> bool:
    """Fallback for when soffice is unavailable: drop the known-empty parts
    that crash Hancom and scrub their refs.

    Removes each present `_DOCX_PROBLEM_PARTS` entry, its `<Override>` in
    `[Content_Types].xml`, and any `<Relationship>` in any `*.rels` whose
    Target points at it (comment parts are referenced from
    word/_rels/document.xml.rels; docProps/custom.xml from _rels/.rels).
    Returns True if the file was modified; no-ops on a non-zip or when no
    problem part is present.
    """
    try:
        with zipfile.ZipFile(path) as zin:
            names = set(zin.namelist())
            drop = {n for n in _DOCX_PROBLEM_PARTS if n in names}
            if not drop:
                return False
            items = [(info, zin.read(info.filename)) for info in zin.infolist()]
    except zipfile.BadZipFile:
        return False

    part_names = "|".join(re.escape("/" + n) for n in drop)
    targets = "|".join(re.escape(n.split("/")[-1]) for n in drop)
    override_re = re.compile(
        r'<Override\b[^>]*\bPartName="(?:' + part_names + r')"[^>]*/>'
    )
    rel_re = re.compile(
        r'<Relationship\b[^>]*\bTarget="(?:[^"]*/)?(?:' + targets + r')"[^>]*/>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, data in items:
            if info.filename in drop:
                continue
            if info.filename == "[Content_Types].xml":
                data = override_re.sub("", data.decode("utf-8")).encode("utf-8")
            elif info.filename.endswith(".rels"):
                data = rel_re.sub("", data.decode("utf-8")).encode("utf-8")
            zout.writestr(info, data)
    path.write_bytes(buf.getvalue())
    return True


_VALID_SCOPES = {"main", "supplementary", "all"}


def export_to_path(
    state: State,
    slug: str,
    *,
    output_path: str,
    fmt: str | None = None,
    csl_path: str | None = None,
    upload_to_storage: bool = True,
    scope: str = "main",
) -> dict:
    """Full export pipeline.

    `fmt` is inferred from output_path extension if None.
    The citation style is auto-resolved from the paper's journal and
    downloaded from the CSL styles repo; pass `csl_path` to override with a
    local CSL file.

    `scope` controls main-vs-supplementary content (a journal receives a main
    manuscript with only the main figures/tables; supplementary items belong
    in a separate file):
      - "main" (default) — full manuscript text + MAIN figures/tables only
        (figure_number / table_number < 100). Supplementary items are excluded.
      - "supplementary" — a standalone 'Supplementary Material' document with
        ONLY the supplementary figures/tables (≥ 101), no main manuscript text.
      - "all" — everything in one file (the pre-split legacy behavior).
    To deliver both, export twice: once with scope="main" and once with
    scope="supplementary" to a second path.

    Returns metadata: local path, blob path (if uploaded), pandoc rc/stderr,
    csl status, plus the prepare_export warnings so the caller can surface
    them.
    """
    scope = (scope or "main").lower()
    if scope not in _VALID_SCOPES:
        raise ValueError(f"invalid scope {scope!r}; choose from {_VALID_SCOPES}")
    include_main = scope in ("main", "all")
    include_supp = scope in ("supplementary", "all")

    bundle = prepare_export(state, slug)
    export_warnings = list(bundle["warnings"])
    out = pathlib.Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    inferred = (out.suffix.lstrip(".") or "").lower()
    fmt = (fmt or inferred or "docx").lower()
    if fmt not in _VALID_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; choose from {_VALID_FORMATS}")

    # Non-"paper" docs (reports / other) render .docx natively via python-docx
    # — pandoc's OOXML crashes Hancom (dev-todo P0-1) and these docs don't need
    # citeproc/CSL. Papers, and any non-docx format, stay on the pandoc path.
    doc_type = (bundle["paper"].get("doc_type") or "paper").lower()
    engine = "docx_native" if (doc_type != "paper" and fmt == "docx") else "pandoc"

    with tempfile.TemporaryDirectory(prefix=f"export-{slug}-") as tmp:
        tmp_path = pathlib.Path(tmp)

        # Which figures/tables go in this file depends on `scope`. The main
        # manuscript carries only main items; the supplementary export carries
        # only supplementary items (in its own document a journal stores
        # separately). "all" keeps both together (legacy).
        main_figs = bundle["figures"] if include_main else []
        supp_figs = bundle["supplementary_figures"] if include_supp else []
        main_tbls = bundle["tables"] if include_main else []
        supp_tbls = bundle["supplementary_tables"] if include_supp else []
        staged_figs = [*main_figs, *supp_figs]

        # Lay out manuscript + bib. Escape '---' rules (dev-todo P1-3), then
        # append Tables/Figures sections so registered items get embedded
        # (dev-todo EXP-1 + tables-appendix). For a supplementary-only export
        # there is no main manuscript text — start from a heading.
        if include_main:
            manuscript_text = _escape_thematic_breaks(bundle["manuscript"])
            manuscript_text = _rewrite_inline_figure_refs(
                manuscript_text, staged_figs, [],
            )
            tbl_heading, fig_heading = "Tables", "Figures"
        else:
            manuscript_text = "# Supplementary Material\n"
            tbl_heading, fig_heading = "Supplementary Tables", "Supplementary Figures"

        # Tables before figures (conventional manuscript order). Both
        # appendices carry markup the body only text-references.
        tbl_appendix = _tables_appendix(main_tbls, supp_tbls, heading=tbl_heading)
        if tbl_appendix:
            manuscript_text = manuscript_text.rstrip() + "\n\n" + tbl_appendix
        fig_appendix = _figures_appendix(main_figs, supp_figs, heading=fig_heading)
        if fig_appendix:
            manuscript_text = manuscript_text.rstrip() + "\n\n" + fig_appendix
        # Convert `{doi:…}` markers to pandoc `[@key]` citations so --citeproc
        # renders them + emits a bibliography. Pandoc-only: docx_native has no
        # citeproc, so its markers stay literal (already warned at prepare).
        if engine == "pandoc":
            manuscript_text, _unmatched_cites = _rewrite_inline_citations(
                manuscript_text, bundle["references"],
            )
        (tmp_path / "manuscript.md").write_text(manuscript_text, encoding="utf-8")
        has_bib = bool(bundle["bibtex"].strip())
        csl_arg: str | None = None
        csl_status = "no_references"
        csl_filename: str | None = None
        # Citation style / bibliography only apply to the pandoc path.
        if has_bib and engine == "pandoc":
            (tmp_path / "references.bib").write_text(bundle["bibtex"], encoding="utf-8")
            csl_arg, csl_status, csl_filename, csl_warnings = _place_csl(
                state, tmp_path, bundle, csl_path,
            )
            export_warnings.extend(csl_warnings)

        # Download figure blobs into tmp dir (only those included in this scope)
        for fig in staged_figs:
            bp = fig.get("blob_path")
            if not bp:
                continue
            data = state.backend.get_blob(bp)
            if data is None:
                continue
            local_name = pathlib.Path(bp).name
            (tmp_path / local_name).write_bytes(data)

        tmp_output = tmp_path / out.name
        docx_hancom_fix = "none"

        if engine == "docx_native":
            # python-docx writes a native package Hancom opens cleanly, so no
            # OOXML normalization is needed. Figure embeds resolve against the
            # staged blobs in tmp_path.
            _docx_export.render_markdown_to_docx(
                manuscript_text, tmp_output, asset_dir=tmp_path,
            )
            docx_hancom_fix = "native_python_docx"
            if has_bib:
                export_warnings.append(
                    "references are not auto-formatted for report/other docs "
                    "(python-docx export has no citeproc) — add a manual "
                    "references section if needed"
                )
        else:
            # Run pandoc; it writes the output file inside tmp dir, we copy out.
            args = _format_pandoc_args(
                fmt, "manuscript.md", out.name,
                has_bib=has_bib, csl_path=csl_arg,
            )
            rc, stdout, stderr = state.require_pandoc().run(args, cwd=str(tmp_path))
            if rc != 0:
                return {
                    "error": f"pandoc failed (rc={rc}): {stderr.strip()}",
                    "warnings": export_warnings,
                }
            if not tmp_output.is_file():
                return {
                    "error": "pandoc reported success but produced no output file",
                    "warnings": export_warnings,
                }

            # Make the .docx open in Hancom Office (dev-todo P0-1): prefer a
            # LibreOffice round-trip (normalizes the whole OOXML package); fall
            # back to stripping the known-problem empty parts when soffice is
            # unavailable. Done before we copy/upload.
            if fmt == "docx":
                if _normalize_docx_via_soffice(tmp_output):
                    docx_hancom_fix = "soffice"
                elif _strip_problem_docx_parts(tmp_output):
                    docx_hancom_fix = "stripped_parts"

        # Copy to the user-specified path
        shutil.copy2(tmp_output, out)
        output_bytes = tmp_output.read_bytes()

    blob_path: str | None = None
    if upload_to_storage:
        blob_path = state.project_path("papers", slug, "exports", out.name)
        state.backend.put_blob(blob_path, output_bytes)
        # Also record an exports doc so the dashboard can list past exports
        doc_path = state.project_path("papers", slug, "exports", out.name)
        # We're storing the export-doc at the same key as the blob — that's fine
        # because docs and blobs have separate stores. Add metadata fields.
        existing = state.backend.get_doc(doc_path)
        meta = {
            "filename": out.name,
            "format": fmt,
            "scope": scope,
            "blob_path": blob_path,
            "size_bytes": len(output_bytes),
            "csl_filename": csl_filename,
            "csl_status": csl_status,
            "updated_at": now_iso(),
        }
        if existing is None:
            meta["created_at"] = meta["updated_at"]
            state.backend.set_doc(doc_path, meta)
        else:
            state.backend.update_doc(doc_path, meta)

    return {
        "slug": slug,
        "format": fmt,
        "scope": scope,
        "doc_type": doc_type,
        "engine": engine,
        "local_path": str(out),
        "blob_path": blob_path,
        "size_bytes": len(output_bytes),
        "csl_filename": csl_filename,
        "csl_status": csl_status,
        "docx_hancom_fix": docx_hancom_fix,
        "warnings": export_warnings,
        "placeholders": bundle["placeholders"],
        "unresolved_citations": bundle["unresolved_citations"],
        "dashboard_url": state.dashboard_url("papers", slug),
    }


def list_exports(state: State, slug: str) -> list[dict]:
    """List previously-exported files for a paper."""
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(state.project_path("papers", slug, "exports"))
    items = [data for _, data in pairs]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items
