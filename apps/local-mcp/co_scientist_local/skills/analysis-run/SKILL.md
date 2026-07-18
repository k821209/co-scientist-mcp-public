---
name: analysis-run
description: Run a computational analysis (local or HPC) within a named group attached to a paper, then map its outputs (PNG/CSV) to manuscript figures/tables. Use when the user says "run analysis," "do X computation," "submit a job," "execute this script," or wants to produce a result figure from data.
---

# /analysis-run

**Triggers:** "run the differential expression analysis," "submit a
GATK pipeline," "compute X from Y data," "do a t-test on …", "make
figure 2 from this CSV."

**This is the DEFAULT path for ANY computation that produces a manuscript
figure, table, or number — not just "big" jobs.** A quick `zcat | awk`, a
one-off `gm_compare`, a plotting script, an ssh command on a registered node:
all of it needs a run record (host · command · env · log · pid) or the
paper's provenance has a silent hole ("which server / which command made
Fig 3?" must be answerable from `analysis_runs`). Never run a result-producing
analysis via raw Bash/ssh and move on. If you already did, **back-fill it now**
with `create_analysis(...)` + `record_analysis_run(host=, command=, …)`, and
reconcile with `scan_untracked_jobs` / `list_analysis_runs`.

## What it does

Wraps a computation in a tracked record on a specific paper:
- `analyses/{name}` — the analysis group doc (description, status)
- `analyses/{name}/runs/{run_key}` — one execution record (command,
  host, start/end, exit code, log tail)
- Optional: outputs (PNG / CSV / TSV) get registered as figures or
  tables on the paper.

The dashboard's Runs tab surfaces every run in real time
(collectionGroup query on `runs`). Logs stream into the run doc via
`refresh_log_tail`.

## Two execution paths

Every run goes **one of two ways**, and you pick per run:

- **Local** — runs on the same machine Claude Code is on, inside the
  project's `analysis/<group>/` folder. Use for quick/light jobs, or
  when no HPC is registered. → `launch_local_job`
- **Server (remote HPC)** — rsyncs the analysis folder to a registered
  server and launches there (nohup or a scheduler like `sbatch`). Use
  for heavy/long jobs. → `submit_remote_job`

The original repo split these the same way; keep them distinct — don't
try to run a remote command through the local tool or vice-versa.

### A. Local (your machine)

```
run = mcp__co_scientist__launch_local_job(
  slug,
  analysis="<group_name>",
  command="bash run.sh",            # runs *inside* workdir
  workdir="analysis/<group>",       # must already exist
  env_name="<conda_env>",           # optional — conda env to activate
  conda_root="~/miniconda3",        # optional — required with env_name
)
```

`workdir` must already exist — the MCP does **not** create it
(`FileNotFoundError` otherwise). Create `analysis/<group>/` and write
the script there first. The command's cwd **is** `workdir`, so use
paths relative to it (`bash run.sh`, not `bash analysis/<group>/run.sh`).

Returns immediately with the PID and a generated `run_key` (in the
returned row — you don't pass one in). The MCP wraps `subprocess.Popen`
so your Claude Code session doesn't block. Periodically poll with the
`run_key` from the return:

```
mcp__co_scientist__reap_local_run(slug, analysis, run["run_key"])
```

When `finished_at` is set, you're done.

### B. Remote (registered HPC alias)

If the user has registered a server (see `add_server`):

```
mcp__co_scientist__submit_remote_job(
  slug,
  analysis="<group_name>",
  command="sbatch run.slurm",       # runs *inside* the remote dir
  server_alias="<server_alias>",
  env_name="<conda_env>",           # optional
  local_dir="analysis/<group>",     # rsync'd to the server before launch
)
```

The remote working dir is derived automatically — it's the server's
`default_workdir` + `/analysis/<group>` (created with `mkdir -p`). You
don't pass a remote path; set `local_dir` to the local folder to rsync
up, and the command runs inside the remote dir. `run_key` is generated
for you (in the returned row).

Streams stderr/stdout back via `tail_remote_log` and
`refresh_log_tail`. Don't `ssh "nohup …"` manually — the run won't be
tracked and the dashboard won't see it.

## Flow

### 1. Decide / create the analysis group

```
analyses = mcp__co_scientist__list_analyses(slug)
```

If no group matches what the user wants, create one:

```
mcp__co_scientist__create_analysis(
  slug, name="<group>", description="<one-liner>"
)
```

Group name must be filesystem-friendly (slug-like): `tair-pangenome-snp`,
not `TAIR pangenome SNP analysis (v2)`.

### 2. Decide / write the script

By convention, scripts live in `analysis/<group>/`:

```
analysis/
└── tair-pangenome-snp/
    ├── run.sh          ← entry point
    ├── filter.py       ← steps as the user prefers
    ├── data/           ← inputs
    └── out/            ← outputs created by run.sh
```

Co-locate scripts with their outputs — no separate scripts folder.

If the user described the analysis but doesn't have a script yet:
1. Draft `run.sh` (and helpers) based on their description.
2. Show it to the user for review.
3. Once approved, save it under `analysis/<group>/`.

### 3. Run

Pick **local or server** based on the job's weight and the user's
setup (see "Two execution paths" above).

For local — set `workdir="analysis/<group>"` so relative paths inside
the script work, and make sure that folder exists first. For server —
set `local_dir="analysis/<group>"`; it gets rsync'd up before launch:

```
mcp__co_scientist__add_server(...)    # one-time per HPC
mcp__co_scientist__list_servers()
mcp__co_scientist__server_status(alias)  # is it up?
```

### 4. Watch + reap

Local:
```
run = mcp__co_scientist__reap_local_run(slug, analysis, run_key)
# loop with a short sleep until run["finished_at"] is set
```

Calling `reap_local_run` is the fastest way to get the result, but it's
no longer the *only* way a run gets closed: a background reaper in the
MCP polls launched local PIDs and auto-marks finished within ~30s, so a
job you killed or that crashed surfaces on the dashboard's Runs tab on
its own (jobs that died between sessions are swept at the next startup).

Remote:
```
mcp__co_scientist__poll_remote_pids(alias)  # PIDs still alive?
mcp__co_scientist__refresh_log_tail(slug, analysis, run_key)
# (the dashboard does this automatically every few seconds)
```

When done, check `exit_code`. If non-zero, surface the log tail.

### 5. Register outputs as figures/tables

Walk `analysis/<group>/out/` (or wherever the script wrote its
outputs). For each PNG/PDF the user wants on the manuscript:

```
mcp__co_scientist__add_figure(
  slug,
  figure_number=N,                 # ≥101 for supplementary
  title="<concise title>",
  caption="<draft 1-sentence caption>",   # full legend later
  local_path="analysis/<group>/out/<file>.png",
)
```

For CSV/TSV that should appear as a table:

```
mcp__co_scientist__add_table(
  slug,
  table_number=N,                  # ≥101 for supplementary
  title="<title>",
  content="<markdown table — convert from CSV>",
  caption="<draft caption>",
)
```

Don't register every output — only those the user wants in the paper.
The rest sit in `analysis/<group>/out/` as the audit trail.

### 6. Update the analysis description

```
mcp__co_scientist__update_analysis(
  slug, name="<group>",
  description="<what was done + which figures/tables came out>"
)
```

This is what shows on the dashboard's analysis card; future you (or
the next agent) reads it to understand what each group does.

## Critical rules

- **NEVER bypass the MCP for run tracking**. `nohup ssh "…"` skips
  the database; the run won't appear in the Runs tab and there's no
  log tail. Use `submit_remote_job` even for one-shot remote work.
- **Output dir per run is fine** but DON'T create a separate
  `analysis/<group>/scripts/` directory. Scripts + outputs in the
  same group folder.
- **Don't overwrite existing PNGs without asking** — they may already
  be registered as figures.
- **300+ DPI for figures**. Common matplotlib idiom:
  `plt.savefig("out/fig1.png", dpi=300, bbox_inches="tight")`.
- **Captions stay short here**; full legends come during paper
  composition. The figure's `legend` field is for the longer text.

## Common follow-up

After a successful run, the user often asks: "show me the figure" or
"is the analysis description on the dashboard right?" Point them at
the Paper page (figures section) and the Runs tab (with the run_key
they can match to logs).
