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
   installed package, so this file rarely needs to change. To update the
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
    """
    path = root / context
    if path.exists():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        if project_id and project_id not in text:
            return {"file": context, "state": "names another project"}
        return {"file": context, "state": "kept"}
    if not project_id:
        return {"file": context, "state": "not written: no --project"}
    path.write_text(render(project_id, config=config, context=context), encoding="utf-8")
    return {"file": context, "state": "written"}
