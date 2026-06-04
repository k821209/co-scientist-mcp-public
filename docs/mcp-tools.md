# MCP tool catalog

All tools registered under `mcp__co_scientist__*`. ~70 total.

The MCP server is single-project — every tool implicitly operates on the
`state.project_id` resolved at startup from the API key in `.mcp.json`.
Slug parameters disambiguate papers within that project.

## Identity / session

| Tool | Purpose |
| --- | --- |
| `whoami()` | Active project_id, owner_uid, project name, guide_version. Call first to verify CLAUDE.md ↔ MCP project match. |
| `project_guide()` | Returns the canonical session guide (skills, conventions, citation/math rules). Source: `co_scientist_local/guide.py`. |

## Papers

`create_paper`, `list_papers`, `get_paper_state`, `update_paper`, `delete_paper`

`get_paper_state(slug)` returns paper + sections + assembled manuscript text in one call.
`delete_paper` cascades all subcollections (sections, reviews, references, figures, tables, analyses, activity_log, verification_findings).

## Sections

`get_section`, `update_section`, `list_sections`, `get_manuscript`

`update_section` regenerates the `manuscript.md` Storage blob on every write.
`get_manuscript(slug)` returns the regenerated text directly (single network round-trip vs assembling client-side).

## Reviews (inline comments)

`add_review`, `list_reviews`, `update_review`, `count_open_user_comments`

Reviews carry `source` (`user` | `agent`) and `status` (`open` | `resolved` | `dismissed`). `count_open_user_comments(slug)` is what the agent calls at session start to surface unhandled user feedback.

## Figures & tables

`add_figure`, `update_figure`, `get_figure`, `list_figures`, `delete_figure`
`add_table`, `update_table`, `get_table`, `list_tables`, `delete_table`

`add_figure(local_path=...)` uploads the PNG to Storage and writes the metadata doc.
`figure_number ≥ 101` ⇒ supplementary figure (same for tables). `list_figures(supplementary=True)` filters.

## References + CrossRef DOI verification

| Tool | Purpose |
| --- | --- |
| `add_reference` | Manual entry — full metadata supplied. |
| `update_reference`, `get_reference`, `list_references`, `search_references`, `delete_reference` | Standard CRUD. |
| `verify_doi(doi)` | Spot-check a single DOI against CrossRef. Raises if 404. **No write.** |
| `add_reference_by_doi(slug, doi, citation_key?)` | Fetch CrossRef metadata, derive citation_key (`smith2024`), refuse if 404. |
| `enrich_reference_from_doi(slug, citation_key)` | Fill blanks on an existing ref. Won't overwrite non-empty fields. |
| `validate_references(slug)` | Bulk CrossRef check. Splits into resolved / unresolved / title_mismatch / missing_doi / errors. Persists each verdict to `verification_findings/`. |
| `list_verification_findings(slug, only_unacknowledged=True, only_problems=True)` | Read what the dashboard's Sync DOIs button (or earlier `validate_references`) found. **Call at session start.** |
| `acknowledge_finding(slug, doi, note?)` | Mark a finding as handled. |
| `clear_findings(slug)` | Wipe before a clean re-validation. |

See [doi-verification.md](doi-verification.md) for the full workflow.

## Analyses + runs

`create_analysis`, `update_analysis`, `get_analysis`, `list_analyses`, `delete_analysis`
`record_analysis_run`, `list_analysis_runs`, `get_analysis_run`, `mark_run_finished`
`launch_local_job`, `reap_local_run`
`submit_remote_job`, `kill_remote_job`, `tail_remote_log`, `refresh_log_tail`
`poll_remote_pids`, `auto_finish_stale_runs`, `scan_untracked_jobs`

Run docs are denormalized with `project_id`, `paper_slug`, `analysis_name` so the dashboard can issue a single `collectionGroup("runs")` query across all of a project's papers.

`refresh_log_tail` persists the last N lines onto the run doc (fields `log_tail`, `log_tail_lines`, `log_tail_updated_at`) so the dashboard sees live progress without SSH access.

## Servers (HPC SSH targets)

`add_server`, `list_servers`, `get_server`, `update_server`, `delete_server`
`add_server_env`, `list_server_envs`, `delete_server_env`, `server_status`

Servers are registered per-project. Environment variables (e.g. conda env paths) are stored as subdocs so `submit_remote_job` can prepend them to the remote command.

## Exports

`prepare_export`, `export_to_path`, `list_exports`

`prepare_export(slug)` returns `math_warnings` (LaTeX violations Pandoc would barf on). Run before export so the agent can fix `n = 69` → `$n = 69$`-style problems.

## Image generation

| Tool | Purpose |
| --- | --- |
| `generate_image(slug, prompt, figure_number?, asset_filename?, aspect_ratio?, model?, caption?)` | Route through `state.image_gen`. Cloud Function path (default) gates on plan. |
| `list_assets(slug)` | List non-figure generated images. |
| `delete_asset(slug, asset_id_or_filename)` | Remove an asset + its Storage blob. |

`model` defaults to `gpt-image-2`. `aspect_ratio` accepts `1:1`/`16:9`/`9:16` aliases mapped to OpenAI's accepted pixel sizes (`1024x1024` / `1536x1024` / `1024x1536`).

## Adding a new tool

1. Implement the logic in `tools/<topic>.py`. Use `_ensure_paper(state, slug)` for any per-paper operation — keeps the "paper not found in project pid=…" error consistent.
2. Register in `mcp_server.py`: import the module, add `@mcp.tool()` function in the relevant section. The docstring is what the agent sees — write it for an LLM, not a human.
3. Bump `GUIDE_VERSION` in `guide.py` and mention the new tool there if it changes the recommended workflow.
4. Tests live in `tests/test_<topic>.py`. The fixtures use `InMemoryBackend` so they're fast.
