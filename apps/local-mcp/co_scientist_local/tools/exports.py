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
from . import figures as _figures
from . import papers as _papers
from . import references as _references
from . import requirements as _requirements
from . import sections as _sections
from . import tables as _tables


_DOI_INLINE_RE = re.compile(r"\{doi:([^}]+)\}")
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


def export_to_path(
    state: State,
    slug: str,
    *,
    output_path: str,
    fmt: str | None = None,
    csl_path: str | None = None,
    upload_to_storage: bool = True,
) -> dict:
    """Full export pipeline.

    `fmt` is inferred from output_path extension if None.
    The citation style is auto-resolved from the paper's journal and
    downloaded from the CSL styles repo; pass `csl_path` to override with a
    local CSL file.
    Returns metadata: local path, blob path (if uploaded), pandoc rc/stderr,
    csl status, plus the prepare_export warnings so the caller can surface
    them.
    """
    bundle = prepare_export(state, slug)
    export_warnings = list(bundle["warnings"])
    out = pathlib.Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    inferred = (out.suffix.lstrip(".") or "").lower()
    fmt = (fmt or inferred or "docx").lower()
    if fmt not in _VALID_FORMATS:
        raise ValueError(f"unsupported format {fmt!r}; choose from {_VALID_FORMATS}")

    with tempfile.TemporaryDirectory(prefix=f"export-{slug}-") as tmp:
        tmp_path = pathlib.Path(tmp)

        # Lay out manuscript + bib
        (tmp_path / "manuscript.md").write_text(bundle["manuscript"], encoding="utf-8")
        has_bib = bool(bundle["bibtex"].strip())
        csl_arg: str | None = None
        csl_status = "no_references"
        csl_filename: str | None = None
        if has_bib:
            (tmp_path / "references.bib").write_text(bundle["bibtex"], encoding="utf-8")
            # Citation style only matters once there's a bibliography.
            csl_arg, csl_status, csl_filename, csl_warnings = _place_csl(
                state, tmp_path, bundle, csl_path,
            )
            export_warnings.extend(csl_warnings)

        # Download figure blobs into tmp dir (main + supplementary)
        for fig in (*bundle["figures"], *bundle["supplementary_figures"]):
            bp = fig.get("blob_path")
            if not bp:
                continue
            data = state.backend.get_blob(bp)
            if data is None:
                continue
            local_name = pathlib.Path(bp).name
            (tmp_path / local_name).write_bytes(data)

        # Run pandoc; it writes the output file inside tmp dir, we copy it out
        tmp_output = tmp_path / out.name
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
        docx_hancom_fix = "none"
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
        "local_path": str(out),
        "blob_path": blob_path,
        "size_bytes": len(output_bytes),
        "csl_filename": csl_filename,
        "csl_status": csl_status,
        "docx_hancom_fix": docx_hancom_fix,
        "warnings": export_warnings,
        "placeholders": bundle["placeholders"],
        "unresolved_citations": bundle["unresolved_citations"],
    }


def list_exports(state: State, slug: str) -> list[dict]:
    """List previously-exported files for a paper."""
    if state.backend.get_doc(state.project_path("papers", slug)) is None:
        raise NotFound(f"paper not found: {slug!r} in project {state.project_id!r}")
    pairs = state.backend.list_collection(state.project_path("papers", slug, "exports"))
    items = [data for _, data in pairs]
    items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return items
