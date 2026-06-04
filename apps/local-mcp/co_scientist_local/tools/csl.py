"""Journal → CSL (Citation Style Language) resolution for export.

A paper's `journal` field decides how citations are formatted. This module
turns a journal name into a Zotero CSL filename, downloads the CSL XML from
the public `citation-style-language/styles` repo, and keeps a per-project
registry so that a once-resolved journal sticks.

Resolution order (`resolve_csl_filename`, no network):
  1. per-project registry  /projects/{pid}/journal_csl/{id}
  2. in-code CSL_JOURNAL_MAP — journals whose CSL slug isn't just the
     kebab-cased name
  3. kebab-case guess of the normalized name

The network fetch (`download_csl`) and the registry auto-write happen in
`export_to_path`, not `prepare_export` — `prepare_export` only resolves the
*filename* so it stays a cheap, offline pre-flight.

Ported from the original co-scientist `resolve_csl` (SQLite registry →
per-project Firestore here).
"""
from __future__ import annotations

import re
import urllib.error
import urllib.request

from ..state import State
from ..util import now_iso

CSL_REPO_BASE = (
    "https://raw.githubusercontent.com/"
    "citation-style-language/styles/master/"
)


class CslNotFound(Exception):
    """The CSL repo has no style matching the resolved filename."""


# Journal-name → Zotero CSL slug. Only journals whose CSL slug is NOT just
# the kebab-cased normalized name need an entry here. Key with
# `_normalize_journal` first.
CSL_JOURNAL_MAP = {
    "nature": "nature",
    "science": "science",
    "cell": "cell",
    "pnas": "pnas",
    "proceedings of national academy of sciences": "pnas",
    "plos one": "plos",
    "plos genetics": "plos-genetics",
    "plos computational biology": "plos-computational-biology",
    "plant cell": "the-plant-cell",
    "plant biotechnology journal": "plant-biotechnology-journal",
    "plant genome": "the-plant-genome",
    "plant journal": "the-plant-journal",
    "plant physiology": "plant-physiology",
    "new phytologist": "new-phytologist",
    "nature genetics": "nature-genetics",
    "nature methods": "nature-methods",
    "nature plants": "nature-plants",
    "nature communications": "nature-communications",
    "bmc genomics": "bmc-genomics",
    "bmc plant biology": "bmc-plant-biology",
    "bmc bioinformatics": "bmc-bioinformatics",
    "genome research": "genome-research",
    "genome biology": "genome-biology",
    "genetics": "genetics",
    "bioinformatics": "bioinformatics",
    "briefings in bioinformatics": "briefings-in-bioinformatics",
    "frontiers in plant science": "frontiers-in-plant-science",
    "molecular plant": "molecular-plant",
    "plant communications": "plant-communications",
    "theoretical and applied genetics": "theoretical-and-applied-genetics",
}


def _normalize_journal(name: str) -> str:
    """Lowercase, strip leading 'the ', punctuation → space, collapse spaces."""
    if not name:
        return ""
    s = name.lower().strip()
    s = re.sub(r"^the\s+", "", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _registry_doc_id(journal: str) -> str:
    """Firestore doc id for a journal's registry row — the normalized name
    with spaces collapsed to '-' (Firestore ids can't contain '/')."""
    norm = _normalize_journal(journal)
    return norm.replace(" ", "-") if norm else ""


# ── per-project registry ─────────────────────────────────────

def lookup_journal_csl(state: State, journal: str) -> str | None:
    """Return the registered csl_filename for `journal`, or None."""
    did = _registry_doc_id(journal)
    if not did:
        return None
    doc = state.backend.get_doc(state.project_path("journal_csl", did))
    if doc and doc.get("csl_filename"):
        return doc["csl_filename"]
    return None


def register_journal_csl(
    state: State, journal: str, csl_filename: str,
    notes: str | None = None,
) -> dict:
    """Add or update the journal → CSL mapping. Idempotent on the normalized
    journal name."""
    norm = _normalize_journal(journal)
    if not norm:
        raise ValueError("journal name is empty after normalization")
    csl_filename = (csl_filename or "").strip()
    if not csl_filename.endswith(".csl"):
        raise ValueError(
            f"csl_filename must end with .csl, got {csl_filename!r}"
        )
    path = state.project_path("journal_csl", norm.replace(" ", "-"))
    existing = state.backend.get_doc(path)
    now = now_iso()
    data = {
        "name": norm,
        "display_name": journal,
        "csl_filename": csl_filename,
        "notes": notes if notes is not None else (existing or {}).get("notes"),
        "created_at": (existing or {}).get("created_at", now),
        "updated_at": now,
    }
    state.backend.set_doc(path, data)
    return data


def list_journal_csls(state: State) -> list[dict]:
    """All registry rows for the project, ordered by normalized name."""
    pairs = state.backend.list_collection(state.project_path("journal_csl"))
    items = [d for _, d in pairs]
    items.sort(key=lambda x: x.get("name", ""))
    return items


def delete_journal_csl(state: State, journal: str) -> bool:
    """Remove the registry row for `journal`. True if a row existed."""
    did = _registry_doc_id(journal)
    if not did:
        return False
    return state.backend.delete_doc(state.project_path("journal_csl", did))


# ── resolution + download ────────────────────────────────────

def resolve_csl_filename(state: State, journal: str | None) -> dict:
    """Resolve a journal name to a CSL filename WITHOUT touching the network.

    Returns:
        {
          csl_filename: str | None,   # e.g. "nature.csl"
          csl_slug: str | None,       # e.g. "nature"
          csl_source: "registry" | "map" | "guess" | None,
          csl_status: "resolved" | "no_journal",
        }
    """
    journal = (journal or "").strip()
    if not journal:
        return {"csl_filename": None, "csl_slug": None,
                "csl_source": None, "csl_status": "no_journal"}

    try:
        registered = lookup_journal_csl(state, journal)
    except Exception:
        registered = None  # never block export on a registry-read failure
    if registered:
        slug = registered[:-4] if registered.endswith(".csl") else registered
        return {"csl_filename": registered, "csl_slug": slug,
                "csl_source": "registry", "csl_status": "resolved"}

    norm = _normalize_journal(journal)
    if norm in CSL_JOURNAL_MAP:
        slug, source = CSL_JOURNAL_MAP[norm], "map"
    else:
        slug, source = norm.replace(" ", "-"), "guess"
    return {"csl_filename": f"{slug}.csl", "csl_slug": slug,
            "csl_source": source, "csl_status": "resolved"}


def download_csl(csl_filename: str, *, timeout: float = 8.0) -> bytes:
    """Fetch a CSL style file from the public CSL styles repo.

    Raises CslNotFound on a 404 or non-CSL content, RuntimeError on other
    network failures.
    """
    url = CSL_REPO_BASE + csl_filename
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise CslNotFound(
                f"no style named {csl_filename!r} in the CSL styles repo"
            ) from e
        raise RuntimeError(f"CSL download failed: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"CSL download failed: {e.reason}") from e
    if not data or b"<style" not in data[:600].lower():
        raise CslNotFound(
            f"{csl_filename!r} did not look like a CSL XML style file"
        )
    return data
