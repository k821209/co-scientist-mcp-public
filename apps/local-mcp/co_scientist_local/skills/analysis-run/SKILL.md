---
name: analysis-run
description: Run a computational analysis (local or HPC) within a named group attached to a paper, with a run record for every execution. Use when the user says "run analysis," "do X computation," "submit a job," "execute this script," or wants to compute a result from data.
---

# /analysis-run

**Triggers:** "run the differential expression analysis," "submit a
GATK pipeline," "compute X from Y data," "do a t-test on …", "run the
plotting script."

**This is the DEFAULT path for ANY computation that produces a manuscript
figure, table, or number — not just "big" jobs.** A quick `zcat | awk`, a
one-off `gm_compare`, a plotting script, an ssh command on a registered node:
all of it needs a run record. The guide's "Analysis provenance" is the rule:
back-filling an ad-hoc run (with its real `started_at` / `finished_at`), the
second ad-hoc run as the signal to start recording, and which of the two
detectors finds a gap after the fact. One thing specific to reconstruction:
`scan_recent_outputs` reports outputs and recorded runs side by side but does
not claim which file came from which command — a run record doesn't declare its
outputs, so that inference is yours to make.

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

Keep them distinct — don't try to run a remote command through the local
tool or vice-versa.

### A. Local (your machine)

```
run = mcp__scivo__launch_local_job(
  slug,
  analysis="<group_name>",
  command="bash run.sh",            # runs *inside* workdir
  workdir="analysis/<group>",       # must already exist
  env_name="<conda_env>",           # optional — conda env to activate
  conda_root="~/miniconda3",        # optional — required with env_name
  params={"model": "...", "lr": 5e-4, "seed": 1, "split": "val"},
)
```

`params` is every argument that could change the result, as a flat dict —
what `compare_run_params` diffs later to tell whether two table rows are a
fair comparison. Not the command string again, and not prose (see the tool's
docstring). Already ran it without? `update_analysis_run(..., params=)`.

`workdir` must already exist — the MCP does **not** create it
(`FileNotFoundError` otherwise). Create `analysis/<group>/` and write
the script there first. The command's cwd **is** `workdir`, so use
paths relative to it (`bash run.sh`, not `bash analysis/<group>/run.sh`).

Returns immediately with the PID and a generated `run_key` (in the
returned row — you don't pass one in). The MCP wraps `subprocess.Popen`
so your session doesn't block. Wait for it with `wait_for_run` (step 4),
using the `run_key` from the return.

### B. Remote (registered HPC alias)

If the user has registered a server (see `add_server`):

```
mcp__scivo__submit_remote_job(
  slug,
  analysis="<group_name>",
  command="sbatch run.slurm",       # runs *inside* the remote dir
  server_alias="<server_alias>",
  env_name="<conda_env>",           # optional
  local_dir="analysis/<group>",     # rsync'd to the server before launch
  params={...},                     # same dict as for the local path
)
```

The remote working dir is derived automatically: the project's root on
that server + `/analysis/<group>` (created with `mkdir -p`). The root is
`<server default_workdir>/<project-slug>`, or the project's
`set_project_workdir` binding; `remote_workdir(alias)` shows it. You
don't pass a remote path; set `local_dir` to the local folder to rsync
up, and the command runs inside the remote dir. `run_key` is generated
for you (in the returned row).

Any `# setup` ssh work for this project — an env, a download, a scratch
dir — goes under that same root. Ask `remote_workdir(alias)` first and use
the path; the guard blocks a `mkdir`/`rsync` outside it.

Streams stderr/stdout back via `tail_remote_log` and
`refresh_log_tail`. Don't `ssh "nohup …"` manually — the run won't be
tracked and the dashboard won't see it.

## Flow

### 1. Decide / create the analysis group

```
analyses = mcp__scivo__list_analyses(slug)
```

If no group matches what the user wants, create one:

```
mcp__scivo__create_analysis(
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
mcp__scivo__add_server(...)    # one-time per HPC
mcp__scivo__list_servers()
mcp__scivo__server_status(alias)  # is it up?
```

### 4. Watch + reap

Local or remote, the wait is one tool:

```
mcp__scivo__wait_for_run(slug, analysis, run_key, timeout_s=…)
```

Do not write the wait yourself — no sleep loop, no shell condition over a
pidfile. The guide's "Analysis provenance" section says why;
`wait_for_run` answers running / finished / **undetermined**, and the third
is the one a hand-written loop cannot give.

**Finished is not succeeded.** When it returns finished, read `exit_code`
and the log (`refresh_log_tail`) before you use any output: non-zero, or a
log that ends in a traceback, is a failed run and is reported as one.

A run you did not wait for still gets closed — the job reports its own end,
and a background reaper marks a dead local PID within about 30 s.

### 5. Register outputs as figures/tables

Walk `analysis/<group>/out/` (or wherever the script wrote its
outputs). For each PNG/PDF the user wants on the manuscript:

```
mcp__scivo__add_figure(
  slug,
  figure_number=N,                 # ≥101 for supplementary
  title="<concise title>",
  caption="<draft 1-sentence caption>",   # full legend later
  local_path="analysis/<group>/out/<file>.png",
  source_analysis="<group>",       # ALWAYS: the analysis that made this file
)
```

For CSV/TSV that should appear as a table:

```
mcp__scivo__add_table(
  slug,
  table_number=N,                  # ≥101 for supplementary
  title="<title>",
  content="<markdown table — convert from CSV>",
  caption="<draft caption>",
  source_analysis="<group>",
)
```

`source_analysis` is what lets `prepare_export` say that a re-run left this
figure or table behind; without it that failure is silent, and a numeric
table without it fails `check_requirements`.

Don't register every output — only those the user wants in the paper.
The rest sit in `analysis/<group>/out/` as the audit trail.

### 6. Update the analysis description

```
mcp__scivo__update_analysis(
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
- **Script hashing, `datasets=` and back-filling `log_path` / `workdir`** are
  in the guide's "Analysis provenance": two runs with identical `params` and an
  edited `run.sh` are NOT comparable, and naming the inputs is what makes
  "which bytes did this read" answerable from the run.
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
