# DOI verification (hallucination check)

Two independent verification axes per citation, set by two different
clients, stored on the same Firestore finding doc:

| Axis | Set by | What it checks | Cost |
| ---- | ------ | -------------- | ---- |
| `doi_verified`     | Browser **Sync DOIs** button, or `validate_references` | Does CrossRef know this DOI? | Cheap (one HTTP) |
| `context_verified` | MCP `validate_references` only                       | Does the manuscript sentence around `{doi:X}` match the paper? | Cheap but needs section text loaded |

A reference is **trusted only when both are `true`**. The dashboard
shows two ribbons per reference (`✓ DOI` / `✓ Context`); a `?` ribbon
means that axis hasn't been checked yet.

## Why

LLMs invent DOIs. The model writes "the Smith 2024 paper on rice domestication
(doi:10.1234/nature.55555)" and the DOI doesn't exist. Spot-checking every
citation manually is the bottleneck this feature removes.

## Source of truth: CrossRef

Public REST API, no auth, generous rate limits:

- `GET https://api.crossref.org/works/{doi}` → 200 with metadata, or 404.

Both implementations send `User-Agent: co-scientist-…` per CrossRef etiquette
and use 150ms inter-request pacing.

## Verdict categories

| Kind | Meaning | Action |
| ---- | ------- | ------ |
| `resolved`        | DOI resolves, all checks pass                          | None — citation is fine |
| `unresolved`      | CrossRef returns 404                                  | **HALLUCINATION** — delete or replace |
| `title_mismatch`  | Stored title doesn't match CrossRef's. Mostly useful BEFORE the first sync; auto-fill makes them equal afterward. | Accept CrossRef title or delete |
| `context_mismatch`| Surrounding sentence around `{doi:X}` in section text shares <2 substantive words with CrossRef title. **THE primary hallucination catcher.** Survives auto-fill. | Delete reference, or correct the DOI |
| `missing_doi`     | Reference has no DOI field                             | Add a DOI, then re-verify       |
| `error`           | Transient (network, 5xx)                               | Retry later                     |

### Why two mismatch categories

`title_mismatch` is structurally weak. It compares the `title` field of
the reference doc against CrossRef's title. As soon as the user runs
"Sync DOIs" (or `enrich_reference_from_doi`), the `title` field is
overwritten with CrossRef's truth — and stays equal forever after.

`context_mismatch` is the real defense. It scans every `{doi:X}` marker
in section bodies, extracts the surrounding sentence, and compares
**that sentence** against the CrossRef title. The agent wrote the
surrounding sentence based on what it BELIEVED the paper was about;
auto-fill can't retroactively rewrite the manuscript text. If the agent
hallucinated a citation (real DOI assigned to an unrelated paper), the
surrounding sentence reveals the intent.

Heuristic: ≥2 substantive words shared between context sentence and
CrossRef title = OK. Below threshold = mismatch.

### Caveats

- **Korean / non-Latin text** — the shared-words check uses `[a-z]+`
  regex, so it can't compare e.g. Korean manuscript context against an
  English CrossRef title. Will always trigger `context_mismatch` (false
  positive). Workaround: keep manuscript text in English.
- **Sparse contexts** — sentences like "(reviewed in {doi:X})" have <3
  substantive words and are skipped from the check (would always false-
  positive). The DOI still counts as resolved if the DOI itself resolves.
- **Cross-paper citation** — citing a foundational paper from a slightly
  different domain ("Drawing on Mendel's work {doi:…}" with a CrossRef
  title containing "pea hybrids") may share few words. Manual review.

## Persistence: `verification_findings/`

```
/projects/{pid}/papers/{slug}/verification_findings/{doi_safe_id}
```

`doi_safe_id` is `re.sub(r"[^a-z0-9]+", "_", doi.lower())` — same DOI hashes
to the same doc on every check, so re-running a sync overwrites rather than
appending.

Schema:
```python
{
  "doi": "10.1234/example",
  "kind": "unresolved" | "title_mismatch" | "missing_doi" | "error" | "resolved",
  "source": "registered_ref" | "inline",
  "ref_citation_key": "smith2024",        # if source == registered_ref
  "stored_title": "...",
  "crossref_title": "...",
  "shared_words": 4,
  "message": "...",                       # if kind == error
  "detected_at": "2026-05-18T12:34:56Z",
  "acknowledged": False,
  "acknowledged_at": "2026-05-18T13:00:00Z",
  "acknowledged_by": "agent" | "user-uid",
  "acknowledged_note": "...",
}
```

## Workflow A — agent self-validates

`validate_references` does NOT decide context fit (word-overlap is too
weak a proxy). It hands the agent a **facts pack** per DOI and the agent
judges:

```
validate_references(slug)
   ├─ unresolved[]   — CrossRef 404 (fake DOI). Server-decidable.
   ├─ missing_doi[]  — ref has no DOI to check.
   ├─ errors[]       — transient lookup failures.
   └─ results[]      — facts pack per resolvable DOI:
                          - crossref: {title, abstract, subjects, authors,
                                       year, journal, type, url}
                          - manuscript_contexts: [{section, sentence,
                              context_before, context_after, stacked_with}]
                          - signals: {title_overlap_words,
                              best_context_overlap_words, ...}

# Agent then judges each result, calling:
acknowledge_finding(slug, doi, verdict="approved"|"rejected", note="...")
# 'approved' → context_verified=true → ribbon turns green
# 'rejected' → context_verified=false → fix or delete

# For unresolved DOIs (server already decided):
delete_reference(slug, citation_key) OR add_reference_by_doi(slug, real_doi)
acknowledge_finding(slug, doi, note="hallucinated, removed")
```

The point: word-overlap fires false positives on stacked citations
("In humans {doi:A}, maize {doi:B}, rice {doi:C}") and on cross-domain
foundational citations. The agent has the manuscript's writing intent
loaded and can judge in context.

## Workflow B — human in the dashboard

The Paper page's References card has a `[Sync DOIs]` button.

1. Scans:
   - All registered references' DOIs
   - Inline `{doi:…}` patterns in section bodies that aren't yet registered
2. Verifies each against CrossRef (sequential, 150ms pacing).
3. Writes the same finding docs.
4. Per-row actions:
   - Resolved inline → **Register as reference** (auto-derives citation_key,
     upgrades the finding's `source` to `registered_ref`).
   - Title mismatch on registered → **Use CrossRef title** (overwrites
     stored title, deletes the finding).
   - Unresolved or mismatch → **Delete reference** (removes the ref doc
     and its finding).
5. Auto-fills missing fields (title/authors/journal/year) from CrossRef
   for resolved registered references — toggle in modal footer.

## Workflow C — handoff between A and B

The point of persisting findings:

- User clicks Sync DOIs in dashboard → 3 hallucinations flagged → user
  closes browser without fixing.
- Next time the agent runs (potentially days later), `list_verification_findings(slug)`
  returns those 3. Agent surfaces them to the user, fixes them, calls
  `acknowledge_finding` on each.

Guide v2026-05-18c instructs every session to call
`list_verification_findings(slug)` at start for each paper.

## Inline DOI scanning

A `{doi:10.1234/example}` pattern in section text isn't a registered
reference — there's no `references/{key}` doc — but it's still subject
to hallucination AND is the source of the context check above.

Both entry points scan section bodies for the pattern:
- **Dashboard**: subtracts already-registered DOIs, queues the remainder
  with `source: "inline"`. Per-row "Register as reference" action.
- **MCP `validate_references()`**: scans all section bodies, builds a
  `doi → [{section, sentence}]` map, runs the context check for every
  DOI it encounters (registered AND inline-only), persists the same
  finding docs.

The context map IS the source of truth for what the agent intended at
write time — it's the only verification signal that survives auto-fill.
