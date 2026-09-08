"""Are the rows of a comparison table actually comparable?

A comparison holds only when its arms differ in the one variable the claim
names. Nothing in the harness could say whether that was true (feedback
d35be8fb8b34): a table carried row names and numbers, the runs that produced
them carried a free-text command, and so two rows that differed in adapter
rank AND objective AND learning rate passed every check the paper had — while
a duplicated sentence or a long caption would have been flagged. A confounded
comparison changes the conclusion; the reporter needed two retrainings once it
was found late.

Three pieces, none of which needs domain knowledge:

  params   — a run records the arguments that define it, as a dict. The
             harness never interprets a value; it only compares.
  varies   — a table (or figure) may declare which keys its rows are SUPPOSED
             to differ in. Optional: without it every difference is listed.
  compare  — the diff. For the runs behind an artifact, every key whose value
             is not the same across them, split into declared and undeclared.
             The judgement stays with a person — a per-arm learning rate can be
             the correct design — so this shows the list and stops.

And an enforcement point, because a mechanism nobody is made to use is a
mechanism that was not there when it mattered (the registration hint was shown
ten times on that paper and acted on zero): `check_requirements` fails a table
that holds numbers and names no analysis. A hand-built table — a primer list,
values compiled from the literature — says so with `source_analysis="manual"`,
which is a statement, not an omission, and satisfies the check.
"""
from __future__ import annotations

import re

from ..backends.base import NotFound
from ..state import State

# "This artifact was not computed." Satisfies the provenance check and is
# skipped by the staleness check; an empty field means UNKNOWN, this means NO.
MANUAL_SOURCE = "manual"

_MISSING = "<missing>"
_NO_PARAMS = "<no params recorded>"


def is_linked(source_analysis: str | None) -> bool:
    """A real analysis link (not empty, not the manual sentinel)."""
    s = (source_analysis or "").strip()
    return bool(s) and s.lower() != MANUAL_SOURCE


def is_manual(source_analysis: str | None) -> bool:
    return (source_analysis or "").strip().lower() == MANUAL_SOURCE


# The hint an artifact's registration returns when it names no analysis.
# Worded by consequence, not by paperwork: "untraceable at submission" read as
# a filing problem and was ignored ten times in a row. What is actually lost is
# the ability to check the comparison the table makes.
NO_PROVENANCE_HINT = (
    "no source_analysis on this artifact. If its numbers were computed, the "
    "harness cannot check whether its rows are comparable — same script "
    "version, same conditions except the one the table claims — and "
    "check_requirements will fail a numeric table left like this. Record the "
    "run (create_analysis + record_analysis_run with params=) and link it with "
    "source_analysis= and source_runs=; for a schematic or a hand-built table "
    "say so with source_analysis=\"manual\"."
)


def normalize_varies(varies) -> list[str] | None:
    """`varies` accepts one key or a list of keys; stored as a sorted list."""
    if varies is None:
        return None
    if isinstance(varies, str):
        items = [v.strip() for v in re.split(r"[,\s]+", varies) if v.strip()]
    else:
        items = [str(v).strip() for v in varies if str(v).strip()]
    return sorted(set(items))


def normalize_params(params) -> dict | None:
    if params is None:
        return None
    if not isinstance(params, dict):
        raise ValueError("params must be a dict of argument name -> value")
    # Keys as strings, values left as given (the harness only compares them).
    return {str(k): v for k, v in params.items()}


# ── numbers in a table ──────────────────────────────────────────────────

_NUMERIC_CELL = re.compile(
    r"^[\s*_]*[-+−]?(?:\d[\d,]*\.?\d*|\.\d+)(?:\s*[eE][-+]?\d+)?\s*%?[\s*_]*"
    r"(?:\s*[±(]\s*[\d.,]+\s*\)?)?[\s*_]*$")


def table_has_numbers(content: str) -> bool:
    """Whether a markdown table has at least one body cell that is a number.

    Header and separator rows are skipped, so a table of primer NAMES with a
    numeric first column of indices still counts — an index column is numbers,
    and the only way to say "not computed" is to say it (MANUAL_SOURCE)."""
    rows = [ln for ln in (content or "").splitlines() if ln.strip().startswith("|")]
    body = [r for r in rows[1:] if not re.match(r"^\s*\|?\s*:?-{2,}", r)]
    for row in body:
        for cell in row.strip().strip("|").split("|"):
            if cell.strip() and _NUMERIC_CELL.match(cell):
                return True
    return False


# ── the diff ────────────────────────────────────────────────────────────

def params_diff(runs: list[dict], declared: list[str] | None = None) -> dict:
    """Every key whose value is not identical across `runs`.

    A key present in some runs and absent in others counts as a difference
    (value `<missing>`): a run recorded under an older script version has a
    different argument set, and that IS the second failure mode. Runs with no
    params at all are listed separately — they cannot be compared, and saying
    so is the point.
    """
    declared = set(declared or [])
    with_params = [r for r in runs if isinstance(r.get("params"), dict)]
    without = [r.get("run_key") for r in runs if not isinstance(r.get("params"), dict)]
    keys: set[str] = set()
    for r in with_params:
        keys.update(r["params"].keys())
    differences: list[dict] = []
    identical: list[str] = []
    for key in sorted(keys):
        values = {r["run_key"]: r["params"].get(key, _MISSING) for r in with_params}
        distinct = {repr(v) for v in values.values()}
        if len(distinct) > 1:
            differences.append({
                "key": key, "declared": key in declared, "values": values,
                "missing_in_some": any(v == _MISSING for v in values.values()),
            })
        else:
            identical.append(key)
    return {
        "runs": [r.get("run_key") for r in with_params],
        "runs_without_params": without,
        "differences": differences,
        "undeclared_differences": [d["key"] for d in differences if not d["declared"]],
        "declared_but_identical": sorted(declared - {d["key"] for d in differences}),
        "identical_keys": identical,
    }


def format_report(label: str, declared: list[str] | None, diff: dict) -> str:
    """The one screen a person reads: what differs, and which of it was meant."""
    lines = [f"{label} — declared: varies={declared or '(none)'}"]
    runs = diff["runs"]
    if not runs:
        lines.append("  no run with params to compare")
    for d in diff["differences"]:
        vals = " vs ".join(f"{d['values'][k]}" for k in runs)
        mark = "declared" if d["declared"] else "NOT declared  ⚠"
        lines.append(f"  {d['key']:<24} {vals:<32} ← {mark}")
    if not diff["differences"] and runs:
        lines.append("  the runs have identical params")
    if diff["declared_but_identical"]:
        lines.append(f"  declared to vary but identical: {', '.join(diff['declared_but_identical'])}  ⚠")
    if diff["runs_without_params"]:
        lines.append(f"  runs with no params recorded (cannot compare): "
                     f"{', '.join(diff['runs_without_params'])}  ⚠")
    return "\n".join(lines)


def compare_run_params(
    state: State,
    slug: str,
    *,
    table_number: int | None = None,
    figure_number: int | None = None,
    analysis: str | None = None,
    run_keys: list[str] | None = None,
) -> dict:
    """Diff the params of the runs behind a table or figure.

    Which runs: the artifact's `source_runs` if it names them; otherwise every
    run of its `source_analysis`. Or bypass the artifact and pass `analysis` (+
    optional `run_keys`) directly.
    """
    from . import runs as _runs
    from . import tables as _tables
    from . import figures as _figures

    declared: list[str] | None = None
    label = "runs"
    if table_number is not None or figure_number is not None:
        if table_number is not None:
            art = _tables.get_table(state, slug, table_number)
            label = f"Table {table_number}"
        else:
            art = _figures.get_figure(state, slug, figure_number)
            label = f"Figure {figure_number}"
        declared = art.get("varies") or None
        src = art.get("source_analysis")
        if is_manual(src):
            return {"item": label, "source_analysis": src, "manual": True,
                    "report": f"{label} is marked manual — nothing to compare."}
        if not is_linked(src):
            return {"item": label, "source_analysis": src, "error":
                    f"{label} has no source_analysis; link it first "
                    f"(update_table/update_figure(source_analysis=, source_runs=))."}
        analysis = analysis or src
        run_keys = run_keys or art.get("source_runs") or None
    if not analysis:
        raise ValueError("give table_number, figure_number, or analysis")
    all_runs = _runs.list_analysis_runs(state, slug, analysis)
    if run_keys:
        by_key = {r.get("run_key"): r for r in all_runs}
        missing = [k for k in run_keys if k not in by_key]
        if missing:
            raise NotFound(f"runs not found under analysis {analysis!r}: {missing}")
        runs = [by_key[k] for k in run_keys]
        selection = "source_runs"
    else:
        runs = sorted(all_runs, key=lambda r: r.get("started_at") or "")
        selection = "all runs of the analysis"
    diff = params_diff(runs, declared)
    return {
        "item": label, "analysis": analysis, "selection": selection,
        "declared_varies": declared, **diff,
        "report": format_report(label, declared, diff),
    }


# ── the enforcement point ───────────────────────────────────────────────

def provenance_check(tables: list[dict], figures: list[dict]) -> dict:
    """The `check_requirements` entry. Fails for a table with numbers in its
    cells and no analysis behind it (and no `manual` statement). Figures are
    listed but do not fail the check: the server cannot tell a bar chart from a
    schematic, and failing a schematic would teach people to link something
    false."""
    failing = [f"Table {t.get('table_number')}" for t in tables
               if table_has_numbers(t.get("content") or "")
               and not is_linked(t.get("source_analysis"))
               and not is_manual(t.get("source_analysis"))]
    unlinked_figures = [f"Figure {f.get('figure_number')}" for f in figures
                        if not is_linked(f.get("source_analysis"))
                        and not is_manual(f.get("source_analysis"))]
    return {
        "name": "table_provenance",
        "label": "Numeric tables name the analysis that produced them",
        "kind": "presence",
        "missing": failing,
        "unlinked_figures": unlinked_figures,
        "ok": not failing,
        "hint": None if not failing else (
            "a table with numbers and no source_analysis cannot be checked for "
            "a confounded comparison. Link it (update_table(source_analysis=, "
            "source_runs=)) or state source_analysis=\"manual\" if it was not "
            "computed."),
    }
