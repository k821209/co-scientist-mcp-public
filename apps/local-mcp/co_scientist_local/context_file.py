"""The project context file a host reads at session start: CLAUDE.md, AGENTS.md.

Tiny on purpose: the project's identity and the four session-start calls. The
rest — skills, the tool surface, conventions — is `project_guide()`, so it
changes with the package instead of with a file in every project directory.

It carries the project id, which is what a later session compares against the
key's binding: without the file that guard is simply skipped. The one-line
install said it wrote this file and did not, for any host (found 2026-11-16);
only the Setup tab's by-hand steps and `scivo setup` did.
"""
from __future__ import annotations

import pathlib

DASHBOARD = "https://co-scientist-5af1a.web.app"

# The server was `co_scientist` until 2026-09-09. A context file written before
# then tells the model to call `mcp__co_scientist__whoami()` — a tool that no
# longer exists — and the guards for the rename read the CONFIG and not this
# file, so a project with a current .mcp.json and an old CLAUDE.md worked in
# every way except its instructions (feedback e76efd026a3b).
LEGACY_PREFIX = "mcp__co_scientist__"
CURRENT_PREFIX = "mcp__scivo__"
CONTEXT_NAMES = ("CLAUDE.md", "AGENTS.md")
_WALK_UP = 8


def stale_context_files(start: pathlib.Path) -> list[tuple[pathlib.Path, int]]:
    """Context files at `start` and above that still call the old server name,
    with how many calls each makes. A host reads the file from every parent
    directory, so every one is looked at — a current one in the parent does
    not excuse a stale one in the project."""
    found: list[tuple[pathlib.Path, int]] = []
    try:
        start = pathlib.Path(start).resolve()
    except OSError:
        return found
    for directory in [start, *start.parents][:_WALK_UP]:
        for name in CONTEXT_NAMES:
            path = directory / name
            try:
                calls = path.read_text(encoding="utf-8").count(LEGACY_PREFIX)
            except OSError:
                continue
            if calls:
                found.append((path, calls))
    return found


def render(project_id: str, *, config: str, context: str) -> str:
    return f"""# Scivo project

Project id: `{project_id}`
Dashboard: {DASHBOARD}/projects/{project_id}/papers

## On session start (every session)

1. Call `mcp__scivo__whoami()` once.
   - Verify the returned `project_id` equals `{project_id}`. If they differ,
     STOP and tell the user — `{config}` and `{context}` were made for
     two different dashboard projects. Have them run the install line from
     the right project's Setup tab again, in this directory.
2. Call `mcp__scivo__project_guide()` for the current skill list,
   tool surface, citation/math/remote conventions. The guide lives in the
   installed package, so this file rarely needs to change — unless a
   session-start notice says the tool names or these calls have changed:
   then run the Setup tab's install line again here, which brings it up to
   date. To update the
   package, run `<python> -m co_scientist_local update` with the
   interpreter `{config}` names — it reads `install_mode` itself and
   does the matching thing (replace a `site-packages` install from git; `git
   pull` an `editable` one, where `pip install --upgrade` is a NO-OP that
   reports success), then re-links the skills. Restart the session either way,
   then confirm with `git_sha`.

**This key is account-wide.** `whoami().key_scope` says the same. It reads
every project this account owns (`list_my_projects`), the account's stored
secrets and its servers registry — not only this project. Never commit it,
never share it as "just this project's key".
3. Call `mcp__scivo__list_papers()` then, for each paper,
   `mcp__scivo__count_open_user_comments(slug)`. If non-zero,
   surface the comments and offer `/paper-revision`.
4. Call `mcp__scivo__count_open_study_questions()`. `from_reader` is
   questions someone left on a study document and is waiting on you —
   read them with `list_study_questions()` and answer with
   `answer_study_question(...)`. `from_agent` is questions a past
   session left for the READER; mention them, don't answer them yourself.
"""


def ensure(root: pathlib.Path, project_id: str | None, *, config: str, context: str) -> dict:
    """Write the file when it is absent; never over one that is there.

    An existing file is the user's — it may hold their own instructions — so
    it is kept, and the reply says whether it names this project: one that
    names another means the mismatch guard will fire, or will not run.

    One thing in it IS changed: a call to the server's old name. That prefix
    can only be a call to a tool that no longer exists, the file is what tells
    the model which tools to call, and re-running this is how an install is
    brought up to date. Everything else in the file is left as it was.
    """
    path = root / context
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        renamed = text.count(LEGACY_PREFIX)
        out: dict = {"file": context}
        if renamed:
            text = text.replace(LEGACY_PREFIX, CURRENT_PREFIX)
            path.write_text(text, encoding="utf-8")
            out["renamed"] = renamed
        out["state"] = ("names another project" if project_id and project_id not in text
                        else "kept")
        return {"file": out["file"], "state": out["state"],
                **({"renamed": renamed} if renamed else {})}
    if not project_id:
        return {"file": context, "state": "not written: no --project"}
    path.write_text(render(project_id, config=config, context=context), encoding="utf-8")
    return {"file": context, "state": "written"}
