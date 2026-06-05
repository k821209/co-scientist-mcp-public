---
name: analysis-audit
description: Audit analysis scripts for hardcoded literals and verify that numbers cited in the manuscript match the live data. Use when the user says "audit the analysis," "check for hardcoded values," "verify the numbers," "is the paper consistent with the data," before export or submission.
---

# /analysis-audit

**Triggers:** "audit the analysis," "check hardcoded paths," "verify
figure 2's numbers," "are the manuscript stats correct," "pre-submission
check."

## Two passes

### Pass 1 — hardcoding scan

Read every script under `analysis/*/` and flag literals that shouldn't
be hardcoded. Severity buckets:

| Severity | Examples                                              | Action |
| -------- | ----------------------------------------------------- | ------ |
| `block`  | absolute user paths (`/Users/…`, `/home/…`), API keys, secrets, hash prefixes pinned to one machine | MUST be removed before submission |
| `warn`   | magic numbers (thresholds, sample counts) with no comment explaining them | verify each is intentional + documented |
| `info`   | config-ish constants that are fine (`N_THREADS = 8`)  | acceptable, no action |

The agent does the scan itself — grep each script for:
- `/Users/`, `/home/`, `C:\\`  → absolute paths
- `sk-`, `AIza`, `ghp_`, long hex strings  → keys / secrets
- bare numeric literals in filter/threshold positions

Produce a triage table. **Don't auto-fix block-level issues** — the
user refactors them (parametrize paths, move secrets to env vars).

### Pass 2 — correctness validation

Verify that numbers cited in the manuscript actually match the data:

1. Read the manuscript: `mcp__co_scientist__get_paper_state(slug)`.
2. Extract every claim-worthy number (sample sizes, p-values, fold
   changes, percentages, counts).
3. For each, trace it back to the analysis output that produced it
   (the CSV in `analysis/<group>/out/`, the figure's source data).
4. Re-derive the number from the live file and compare.
5. Flag any mismatch: "Abstract says n=69 but
   `analysis/cohort/out/samples.csv` has 71 rows."

Where the user wants a durable contract, write an
`audit_sentinels.yaml` next to the analysis:

```yaml
# analysis/de-genes/audit_sentinels.yaml
- type: csv_count
  file: out/significant.csv
  filter: "padj < 0.05"
  expect: 142
  claim: "142 genes were differentially expressed (Results)"
- type: manuscript_match
  pattern: "142 (genes|loci)"
  expect: present
- type: csv_cell
  file: out/summary.csv
  row: 0
  column: mean_coverage
  expect: 31.4
  tolerance: 0.1
```

Re-run the sentinels each time the analysis changes — they're the
trust contract for cited numbers.

## Hard rules

- **No auto-fix of `block` issues.** Surface them; the user refactors.
- **Don't loosen a tolerance to make a check pass.** A failing
  sentinel means the data and the manuscript disagree — fix the
  underlying discrepancy, don't paper over it.
- **Sentinel YAMLs are trust contracts.** Every claim-worthy number
  in the manuscript should have a sentinel. No cited number without
  a check behind it.
- **Block escalation:** if Pass 1 leaves any `block`-level hit, advise
  the user NOT to run `/paper-export` until it's resolved. Hardcoded
  paths / secrets must not ship in a release.

## Output

A report with:
- Pass 1: the triage table (block / warn / info counts + each hit)
- Pass 2: per-number verification (✓ matches / ✗ mismatch with the
  file + expected vs actual)
- A go / no-go recommendation for `/paper-export` and
  `/release-publish`.
