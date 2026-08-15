"""Dataset registry — where a project's source data lives and how it is keyed.

Path:
    doc: projects/{pid}/datasets/{name}

`add_server` records which MACHINES exist; nothing recorded which DATA sat on
them. Three failures came out of that gap in one session (feedback 68c41dc91fef):

  1. Sample metadata lived on a third server nobody knew to look at, so the
     session concluded "rice and tomato have no tissue information", narrowed the
     design, and had to re-run two finished analyses once the user mentioned it
     in passing. Tissue assignment went 33% -> 81% with the data that existed the
     whole time.
  2. Four identifier conventions in one project (`PRAM_267.1.p1`,
     `Os01t0100100-01`, `Glyma.01G000100`, `Solyc00g005000`), discovered by
     opening files one at a time. A mismatch here does not raise — it shows up as
     "the signal is weak", which is why this project had already rewritten an
     entire paper after misreading labels.
  3. The same genome FASTA in five directories with nothing marking the canonical
     copy.

So the registry is designed around the three things that were missing, not
around describing data in general:

  - `server_alias` + `path`  — WHERE. Fixes (1).
  - `id_convention`          — HOW IT IS KEYED, with a real example. Fixes (2).
  - `joins_with`             — WHAT IT CONNECTS TO, **including the negatives**.
    "tomato expression does NOT join SL.gff (separate assembly)" is the entry
    that would have saved half a day, and a schema that can only express
    positive links cannot hold it. Hence the explicit `joins` boolean.
  - `canonical` / `superseded_by` — WHICH COPY. Fixes (3).

`check_dataset` deliberately reports DRIFT, not just existence: "the path is
still there" is the presence answer, and the useful one is "it is 3 GB bigger
than when you recorded 12,345 records".
"""
from __future__ import annotations

import pathlib
import shlex

from ..backends.base import NotFound
from ..state import State
from ..util import now_iso, slugify

KINDS = (
    "expression_matrix", "annotation", "genome", "metadata",
    "reads", "variants", "alignment", "phenotype", "other",
)


def _dataset_path(state: State, name: str) -> str:
    return state.project_path("datasets", name)


def _norm(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("name is required")
    return slugify(name) or name.strip()


def _norm_joins(joins_with) -> list[dict]:
    """Normalize `joins_with` to [{dataset, key, joins, note}].

    A bare string means "joins, key unspecified". `joins=False` is a FIRST-CLASS
    entry, not a degenerate one: recording that two datasets cannot be linked is
    the whole point (see the module docstring).
    """
    out: list[dict] = []
    for j in joins_with or []:
        if isinstance(j, str):
            out.append({"dataset": j.strip(), "key": None, "joins": True,
                        "note": None})
            continue
        if not isinstance(j, dict):
            continue
        target = str(j.get("dataset") or "").strip()
        if not target:
            continue
        out.append({
            "dataset": target,
            "key": (str(j["key"]).strip() if j.get("key") else None),
            # Absent means it DOES join; you have to say so to record a negative.
            "joins": bool(j.get("joins", True)),
            "note": (str(j["note"]).strip() if j.get("note") else None),
        })
    return out


def register_dataset(
    state: State,
    *,
    name: str,
    path: str,
    kind: str = "other",
    server_alias: str | None = None,
    id_convention: str | None = None,
    joins_with: list | None = None,
    canonical: bool = True,
    superseded_by: str | None = None,
    n_records: int | None = None,
    notes: str | None = None,
    overwrite: bool = False,
) -> dict:
    """Register where a dataset lives and how it is keyed.

    `server_alias=None` means the path is local. `kind` is one of KINDS.
    `id_convention` should carry a REAL example identifier, not a description —
    "Glyma.01G000100 (Wm82.a4 gene ids)" is usable, "soybean gene ids" is not.
    """
    dsid = _norm(name)
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}, got {kind!r}")
    if not path or not path.strip():
        raise ValueError("path is required")
    if server_alias:
        from .servers import get_server
        get_server(state, server_alias)   # raises NotFound on a typo'd alias
    doc_path = _dataset_path(state, dsid)
    existing = state.backend.get_doc(doc_path)
    if existing is not None and not overwrite:
        raise ValueError(
            f"dataset {dsid!r} already exists — pass overwrite=True to replace")
    now = now_iso()
    doc = {
        "name": dsid,
        "display_name": name.strip(),
        "server_alias": server_alias,
        "path": path.strip(),
        "kind": kind,
        "id_convention": id_convention,
        "joins_with": _norm_joins(joins_with),
        "canonical": bool(canonical),
        "superseded_by": superseded_by,
        "n_records": n_records,
        "notes": notes,
        # Filled by check_dataset; None means NEVER VERIFIED, which is different
        # from "verified and absent".
        "exists": existing.get("exists") if existing else None,
        "size_bytes": existing.get("size_bytes") if existing else None,
        "mtime": existing.get("mtime") if existing else None,
        "checked_at": existing.get("checked_at") if existing else None,
        "papers": existing.get("papers", []) if existing else [],
        "analyses": existing.get("analyses", []) if existing else [],
        "created_at": existing.get("created_at", now) if existing else now,
        "updated_at": now,
    }
    state.backend.set_doc(doc_path, doc)
    return doc


def update_dataset(state: State, name: str, **fields) -> dict:
    """Patch a dataset record. Only the supplied fields change."""
    dsid = _norm(name)
    doc_path = _dataset_path(state, dsid)
    existing = state.backend.get_doc(doc_path)
    if existing is None:
        raise NotFound(f"dataset not found: {dsid!r}")
    allowed = {"path", "kind", "server_alias", "id_convention", "joins_with",
               "canonical", "superseded_by", "n_records", "notes",
               "display_name"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}; "
                         f"choose from {', '.join(sorted(allowed))}")
    patch = {k: v for k, v in fields.items() if v is not None}
    if "kind" in patch and patch["kind"] not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if "joins_with" in patch:
        patch["joins_with"] = _norm_joins(patch["joins_with"])
    patch["updated_at"] = now_iso()
    state.backend.update_doc(doc_path, patch)
    return state.backend.get_doc(doc_path)


def get_dataset(state: State, name: str) -> dict:
    doc = state.backend.get_doc(_dataset_path(state, _norm(name)))
    if doc is None:
        raise NotFound(f"dataset not found: {name!r}")
    return doc


def list_datasets(
    state: State,
    *,
    kind: str | None = None,
    server_alias: str | None = None,
    canonical_only: bool = False,
) -> list[dict]:
    """Every registered dataset, newest-updated first.

    Call this BEFORE deciding what data a project has. The reported failure was
    concluding "rice and tomato have no tissue information" after searching two
    of three servers — the registry is the answer to "what else is there".
    """
    rows = [d for _, d in state.backend.list_collection(
        state.project_path("datasets"))]
    if kind:
        rows = [d for d in rows if d.get("kind") == kind]
    if server_alias:
        rows = [d for d in rows if d.get("server_alias") == server_alias]
    if canonical_only:
        rows = [d for d in rows if d.get("canonical", True)]
    rows.sort(key=lambda d: d.get("updated_at") or "", reverse=True)
    return rows


def delete_dataset(state: State, name: str) -> bool:
    return state.backend.delete_doc(_dataset_path(state, _norm(name)))


def link_dataset(
    state: State,
    name: str,
    *,
    paper: str | None = None,
    analysis: str | None = None,
) -> dict:
    """Attach a dataset to a paper and/or one of its analyses.

    What makes an "Availability of data and materials" statement writable from
    the record instead of reassembled by hand every time.
    """
    dsid = _norm(name)
    doc = get_dataset(state, dsid)
    if not paper and not analysis:
        raise ValueError("pass paper= and/or analysis=")
    papers = list(doc.get("papers") or [])
    analyses = list(doc.get("analyses") or [])
    if paper:
        from .papers import _paper_path
        if state.backend.get_doc(_paper_path(state, paper)) is None:
            raise NotFound(f"paper not found: {paper!r}")
        if paper not in papers:
            papers.append(paper)
    if analysis:
        if not paper:
            raise ValueError("analysis= also needs paper= (analyses live under a paper)")
        entry = f"{paper}/{analysis}"
        if entry not in analyses:
            analyses.append(entry)
    state.backend.update_doc(_dataset_path(state, dsid), {
        "papers": papers, "analyses": analyses, "updated_at": now_iso()})
    return get_dataset(state, dsid)


def datasets_for_paper(state: State, slug: str) -> list[dict]:
    """Datasets linked to `slug` — the raw material for a data-availability
    statement."""
    return [d for d in list_datasets(state) if slug in (d.get("papers") or [])]


_STAT_SENTINEL = "__CS_DS_OK__"


def check_dataset(state: State, name: str, *, count_lines: bool = False) -> dict:
    """Verify a dataset's path and report DRIFT since it was last checked.

    Not just "does the path exist". Existence is the presence answer and it is
    nearly useless: the failure that matters is a file that is still there but no
    longer the file you recorded. So this compares size and mtime against the
    stored values and says what moved.

    `count_lines` runs `wc -l`, which reads the whole file — off by default
    because a multi-GB matrix makes that a minutes-long call. When on, the count
    is compared against the recorded `n_records`.
    """
    dsid = _norm(name)
    doc = get_dataset(state, dsid)
    path = doc["path"]
    alias = doc.get("server_alias")
    prev = {"exists": doc.get("exists"), "size_bytes": doc.get("size_bytes"),
            "mtime": doc.get("mtime"), "checked_at": doc.get("checked_at")}

    if alias:
        from .servers import get_server
        server = get_server(state, alias)
        ssh = state.require_ssh()
        q = shlex.quote(path)
        cmd = (f"echo {_STAT_SENTINEL}; "
               f"if [ -e {q} ]; then "
               f"du -sb {q} 2>/dev/null | cut -f1; "
               f"date -u -r {q} +%Y-%m-%dT%H:%M:%SZ; "
               + (f"find {q} -maxdepth 0 -type f -exec wc -l {{}} + 2>/dev/null "
                  f"| awk '{{print $1}}'; " if count_lines else "echo; ")
               + f"else echo MISSING; fi")
        rc, out, err = ssh.run(server, cmd, timeout=120 if count_lines else 30)
        if _STAT_SENTINEL not in (out or ""):
            # The remote shell never ran. Reporting exists=False here would be a
            # lie that reads as "your data is gone".
            return {**doc, "checked": False,
                    "error": (err or "").strip() or f"ssh rc={rc}"}
        body = (out or "").split(_STAT_SENTINEL, 1)[1].strip().splitlines()
        if not body or body[0].strip() == "MISSING":
            exists, size, mtime, lines = False, None, None, None
        else:
            exists = True
            size = int(body[0]) if body[0].strip().isdigit() else None
            mtime = body[1].strip() if len(body) > 1 and body[1].strip() else None
            lines = (int(body[2]) if len(body) > 2 and body[2].strip().isdigit()
                     else None)
    else:
        p = pathlib.Path(path).expanduser()
        exists = p.exists()
        size = None
        mtime = None
        lines = None
        if exists:
            st = p.stat()
            size = st.st_size if p.is_file() else None
            from datetime import datetime, timezone
            mtime = (datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                     .strftime("%Y-%m-%dT%H:%M:%SZ"))
            if count_lines and p.is_file():
                with p.open("rb") as fh:
                    lines = sum(1 for _ in fh)

    now = now_iso()
    changes: list[str] = []
    if prev["checked_at"]:
        if prev["exists"] and not exists:
            changes.append("the path has DISAPPEARED since the last check")
        elif (prev["size_bytes"] is not None and size is not None
              and size != prev["size_bytes"]):
            changes.append(
                f"size changed {prev['size_bytes']} → {size} bytes")
        if (prev["mtime"] and mtime and mtime != prev["mtime"]
                and not changes):
            changes.append(f"modified since the last check ({mtime})")
    elif not exists:
        changes.append("the path does not exist")
    if (lines is not None and doc.get("n_records") is not None
            and lines != doc["n_records"]):
        changes.append(
            f"line count {lines} does not match the recorded n_records "
            f"{doc['n_records']}")

    state.backend.update_doc(_dataset_path(state, dsid), {
        "exists": exists, "size_bytes": size, "mtime": mtime,
        "checked_at": now, "updated_at": now})
    return {
        **get_dataset(state, dsid),
        "checked": True,
        "line_count": lines,
        "changed": bool(changes),
        "changes": changes,
    }
