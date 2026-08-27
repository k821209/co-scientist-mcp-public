"""FastMCP server: registers tool functions for Claude Code over stdio."""
from __future__ import annotations

from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as _e:                       # pragma: no cover — env-dependent
    # An incompatible `mcp` is the one dependency failure a user cannot diagnose.
    # The server dies during import, so Claude Code shows only CONNECTION_CLOSED
    # in `claude mcp list` and the real cause — a bare ModuleNotFoundError — is
    # buried in a stdio stderr stream nobody thinks to read (feedback
    # 01606ac4f264: a fresh install resolved mcp 2.0.0, which renamed FastMCP to
    # MCPServer, and it cost a debugging session). So say what happened, which
    # version is installed, and the exact command that fixes it.
    def _installed_mcp_version() -> str:
        try:
            from importlib.metadata import version
            return version("mcp")
        except Exception:
            return "unknown"

    raise ImportError(
        f"co-scientist-local needs the `mcp` package in the 1.2–1.x range; "
        f"mcp {_installed_mcp_version()} is installed and does not provide "
        f"`mcp.server.fastmcp.FastMCP` (mcp 2.0 renamed it to MCPServer under "
        f"mcp.server.mcpserver). Fix with:\n"
        f"    pip install 'mcp>=1.2,<2'\n"
        f"then restart Claude Code. Original error: {_e}"
    ) from _e

from .guide import GUIDE_VERSION, render_guide
from .state import State
from .util import now_iso
from .tools import activity as _activity
from .tools import analyses as _analyses
from .tools import csl as _csl
from .tools import decks as _decks
from .tools import deck_render as _deck_render
from .tools import exports as _exports
from .tools import feedback as _feedback
from .tools import imports as _imports
from .tools import figures as _figures
from .tools import figure_lint as _figure_lint
from .tools import plan as _plan
from .tools import secrets as _secrets
from .tools import authors as _authors
from .tools import affiliations as _affiliations
from .tools import manuscript_lint as _manuscript_lint
from .tools import legend_lint as _legend_lint
from .tools import images as _images
from .tools import assets as _assets
from .tools import cross_project as _cross
from .tools import discussion as _discussion
from .tools import publications as _publications
from .tools import studies as _studies
from .tools import submissions as _submissions
from .tools import graphs as _graphs
from .tools import materials as _materials
from .tools import memory as _memory
from .tools import papers as _papers
from .tools import pipelines as _pipelines
from .tools import references as _references
from .tools import reorder as _reorder
from .tools import requirements as _requirements
from .tools import reviews as _reviews
from .tools import runs as _runs
from .tools import sections as _sections
from .tools import datasets as _datasets
from .tools import servers as _servers
from .tools import workdirs as _workdirs
from .tools import ssh_ops as _ssh_ops
from .tools import tables as _tables
from .tools import todos as _todos
from .tools import verification as _verification
from .tools import videos as _videos
from .tools import youtube as _youtube
from . import features as _features


def build_mcp(state: State) -> FastMCP:
    """Construct the MCP server bound to a given State (uid + backend)."""
    mcp = FastMCP("co-scientist-local")

    # ─── session / identity ──────────────────────────────────────────────────
    @mcp.tool()
    def whoami() -> dict[str, Any]:
        """Return the active project context this MCP is bound to.

        Call once on session start to verify the MCP's project_id matches
        the one your CLAUDE.md mentions. Mismatch means the user mixed
        `.mcp.json` and `CLAUDE.md` from different dashboard projects —
        stop and tell them.

        Also answers "what is actually running?" — `package_path`,
        `python_executable`, `install_mode` and `git_sha`. For an editable
        install `pip show` reports the version frozen at install time (0.0.1
        forever), so a user who pulled the source and restarted has no other way
        to tell whether the new code is live. If they ask whether an update took
        effect, read these, not the version alone.
        """
        info: dict[str, Any] = {
            "project_id": state.project_id,
            "owner_uid": state.owner_uid,
            "guide_version": GUIDE_VERSION,
        }
        try:
            proj = state.backend.get_doc(f"projects/{state.project_id}")
            if proj:
                info["project_name"] = proj.get("name")
                info["project_description"] = proj.get("description")
        except Exception as e:
            info["project_lookup_error"] = str(e)
        # Staleness check: nudge the user to update if this install is behind
        # the latest published build (recently-fixed bugs may already be gone).
        try:
            from .version_check import check_version, runtime_info
            info.update(check_version())
            info.update(runtime_info())
        except Exception:
            pass
        # Record the build this project last ran, so dashboard/human-filed
        # feedback can be correlated with a version too (agent feedback already
        # stamps operating_version). Best-effort — never break whoami.
        try:
            from .version_check import git_sha, installed_version
            sha = git_sha()
            info["git_sha"] = sha
            state.backend.update_doc(f"projects/{state.project_id}", {
                "last_mcp_version": installed_version() or "unknown",
                "last_guide_version": GUIDE_VERSION,
                "last_git_sha": sha,
                "last_active_at": now_iso(),
            })
        except Exception:
            pass
        return info

    @mcp.tool()
    def project_guide() -> str:
        """Return the current session guide (skills, tool surface, citation
        format, math mode rules, remote-job rule, image-gen tier).

        Lives in the installed `co_scientist_local` package so updates flow
        via `pip install --upgrade` — no need to re-download CLAUDE.md.
        """
        return render_guide(include_video=_features.video_enabled())

    # ─── project memory ──────────────────────────────────────────────────────
    @mcp.tool()
    def get_project_memory() -> dict[str, Any]:
        """Read this project's durable memory — a markdown document of soft
        project knowledge (user preferences, decisions, approaches tried,
        gotchas). Cloud-stored, shared, and shown in the dashboard's
        Memory tab. Read it at session start; it is standing context.
        Returns {content, updated_at, updated_by}.
        """
        return _memory.get_project_memory(state)

    @mcp.tool()
    def append_project_memory(note: str) -> dict[str, Any]:
        """Append one durable fact to the project memory (a new line).
        Use for knowledge NOT recoverable from papers/reviews/figures —
        e.g. a user writing preference, a decision and its reason, an
        approach that was tried and rejected, a domain gotcha.
        """
        return _memory.append_project_memory(state, note)

    @mcp.tool()
    def update_project_memory(content: str) -> dict[str, Any]:
        """Replace the whole project-memory markdown document. Use when
        reorganizing or pruning; for a single new fact prefer
        append_project_memory.
        """
        return _memory.update_project_memory(state, content)

    @mcp.tool()
    def get_project_skills() -> dict[str, Any]:
        """Return the project's user-defined skills/playbooks (from the Memory
        tab): {content, updated_at, updated_by}. Read at session start and
        follow them for THIS project — freeform, project-scoped instructions
        that complement the built-in skills. `content` is "" when none set."""
        return _memory.get_project_skills(state)

    @mcp.tool()
    def update_project_skills(content: str) -> dict[str, Any]:
        """Replace the whole project-skills markdown document."""
        return _memory.update_project_skills(state, content)

    # ─── project to-dos & activity timeline ──────────────────────────────────
    @mcp.tool()
    def add_todo(text: str, paper_slug: str | None = None) -> dict[str, Any]:
        """Add a to-do item to this project's shared checklist, visible on the
        dashboard's Activity tab. Use it to record planned work so the human
        collaborator sees what's queued. Optionally tie it to a paper via
        `paper_slug`. Returns the created item (with its id).
        """
        return _todos.add_todo(state, text, paper_slug=paper_slug)

    @mcp.tool()
    def list_todos(status: str | None = None) -> list[dict[str, Any]]:
        """List the project's to-do items (oldest first). Optionally filter by
        status: "open", "in_progress", or "done".
        """
        return _todos.list_todos(state, status=status)

    @mcp.tool()
    def update_todo(
        todo_id: str,
        status: str | None = None,
        text: str | None = None,
    ) -> dict[str, Any]:
        """Update a to-do's status ("open"/"in_progress"/"done") and/or text.
        Marking one "done" also records it on the project timeline.
        """
        return _todos.update_todo(state, todo_id, status=status, text=text)

    @mcp.tool()
    def log_activity(
        title: str,
        detail: str | None = None,
        paper_slug: str | None = None,
    ) -> dict[str, Any]:
        """Post a free-form note to the project's activity timeline (a "what I
        did / decided" entry the human sees on the Activity tab). For routine
        writes (creating papers, editing sections, comments) the timeline is
        populated automatically — use this for milestones or decisions that
        wouldn't otherwise show up.
        """
        _activity.log_timeline(
            state, event_type="note", title=title,
            detail={"text": detail} if detail else None, paper_slug=paper_slug,
        )
        return {"ok": True}

    @mcp.tool()
    def list_activity(limit: int = 30) -> list[dict[str, Any]]:
        """Return the most recent project timeline entries (newest first):
        automatic events (paper/section/review changes, todo activity) plus any
        notes logged with log_activity.
        """
        return _activity.list_timeline(state, limit=limit)

    # ─── papers ──────────────────────────────────────────────────────────────
    @mcp.tool()
    def create_paper(
        title: str,
        slug: str | None = None,
        authors: list[str] | None = None,
        journal: str | None = None,
        abstract: str | None = None,
        doc_type: str = "paper",
    ) -> dict[str, Any]:
        """Create a new document and seed sections.

        doc_type is one of "paper", "report", "other". Only "paper" seeds the
        canonical section scaffold (abstract/intro/methods/results/discussion/
        conclusion); "report" and "other" start with no sections so the author
        structures them freely. doc_type also drives export: non-paper docs
        export to .docx via python-docx (native, Hancom-friendly) instead of
        pandoc.
        """
        return _papers.create_paper(
            state, title=title, slug=slug, authors=authors,
            journal=journal, abstract=abstract, doc_type=doc_type,
        )

    @mcp.tool()
    def list_papers(
        summary: bool = False,
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List all papers for the active user.

        `summary=True` returns just slug/title/journal/doc_type/status/dates —
        use it for the session-start "what papers exist" call. The full record
        includes each paper's journal-requirements notes, so a project with
        several papers spends a lot of context answering a small question.
        `fields=[...]` picks explicitly; `slug` is always included."""
        return _papers.list_papers(state, summary=summary, fields=fields)

    @mcp.tool()
    def import_document(
        local_path: str,
        extract_media_to: str | None = None,
    ) -> dict[str, Any]:
        """Convert an existing manuscript file to markdown so it can be
        imported as a paper.

        Supported: .docx / .odt / .rtf / .html / .tex / .epub / .md
        (pandoc — preserves headings + embedded images) and .pdf
        (pypdf text extraction — LOSSY: no section structure, no
        figures).

        Returns {source_format, markdown, media[], warnings[],
        char_count}. The MCP only converts — splitting the markdown
        into canonical sections is the agent's job (see /paper-import).
        """
        return _imports.import_document(
            state, local_path=local_path, extract_media_to=extract_media_to,
        )

    @mcp.tool()
    def get_paper_state(slug: str) -> dict[str, Any]:
        """Return paper + sections + assembled manuscript text."""
        return _papers.get_paper_state(state, slug)

    @mcp.tool()
    def update_paper(
        slug: str,
        title: str | None = None,
        journal: str | None = None,
        status: str | None = None,
        target_date: str | None = None,
        authors: list[str] | None = None,
        abstract: str | None = None,
        doc_type: str | None = None,
    ) -> dict[str, Any]:
        """Patch a paper's metadata. doc_type is one of "paper"/"report"/"other".

        `abstract` updates the metadata field and mirrors into the abstract
        section body (the text the dashboard renders and export reads).
        """
        return _papers.update_paper(
            state, slug, title=title, journal=journal, status=status,
            target_date=target_date, authors=authors, abstract=abstract,
            doc_type=doc_type,
        )

    @mcp.tool()
    def delete_paper(slug: str) -> dict[str, Any]:
        """Delete a paper and all its sections/reviews/manuscript blob."""
        return {"deleted": _papers.delete_paper(state, slug)}

    # ─── journal/paper-type requirements ─────────────────────────────────────
    @mcp.tool()
    def set_paper_requirements(
        slug: str,
        paper_type: str,
        abstract_max_words: int | None = None,
        abstract_structured: bool | None = None,
        main_text_max_words: int | None = None,
        max_figures: int | None = None,
        max_tables: int | None = None,
        max_display_items: int | None = None,
        max_references: int | None = None,
        required_sections: list[str] | None = None,
        notes: str | None = None,
        source: str | None = None,
    ) -> dict[str, Any]:
        """Store this paper's journal + paper-type submission spec.

        Fill the fields from the journal's *current* author guidelines for
        the chosen paper type (Article, Short Communication, Letter,
        Review, …). Leave a limit None when the guidelines state none —
        never invent one. Put rules that don't fit a field in `notes`
        (e.g. "Methods at the end", "structured abstract"). `source` is
        the guidelines URL. See the /journal-requirements skill.
        """
        return _requirements.set_paper_requirements(
            state, slug, paper_type=paper_type,
            abstract_max_words=abstract_max_words,
            abstract_structured=abstract_structured,
            main_text_max_words=main_text_max_words,
            max_figures=max_figures, max_tables=max_tables,
            max_display_items=max_display_items, max_references=max_references,
            required_sections=required_sections, notes=notes, source=source,
        )

    @mcp.tool()
    def check_requirements(slug: str) -> dict[str, Any]:
        """Measure the manuscript against its stored journal spec.

        Deterministic signal provider: counts abstract/main-text words,
        figures, tables, references and compares to the limits. Returns
        {configured, requirements, metrics, checks, violations, ok}.
        Judgment calls (structured-abstract format, free-text `notes`)
        are yours — read `requirements` and decide.
        """
        return _requirements.check_requirements(state, slug)

    # ─── sections ────────────────────────────────────────────────────────────
    @mcp.tool()
    def get_section(slug: str, key: str) -> dict[str, Any]:
        """Read one section's body + metadata."""
        return _sections.get_section(state, slug, key)

    @mcp.tool()
    def update_section(
        slug: str,
        key: str,
        body: str | None = None,
        status: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Update a section's body/status/title; regenerates the manuscript blob."""
        return _sections.update_section(state, slug, key, body=body, status=status, title=title)

    @mcp.tool()
    def add_section(
        slug: str,
        key: str,
        title: str,
        sort_order: float,
        body: str = "",
    ) -> dict[str, Any]:
        """Add a custom section beyond the 6 canonical ones (e.g. an
        overview/memo/review-response doc). `key` must be unique;
        `sort_order` positions it among existing sections (canonical
        sections are seeded at 1..6, so use fractions like 0.5 or 2.5 to
        slot between them). Regenerates the manuscript blob."""
        return _sections.add_section(
            state, slug, key=key, title=title,
            sort_order=sort_order, body=body,
        )

    @mcp.tool()
    def delete_section(slug: str, key: str) -> bool:
        """Delete a section (canonical or custom); regenerates the manuscript
        blob. Returns True if the section existed, False otherwise."""
        return _sections.delete_section(state, slug, key)

    @mcp.tool()
    def reorder_section(slug: str, key: str, sort_order: float) -> dict[str, Any]:
        """Set a section's sort_order to re-position it in the manuscript.
        Use fractions (e.g. 2.5) to slot between existing sections without
        touching the rest. Regenerates the manuscript blob."""
        return _sections.reorder_section(state, slug, key, sort_order=sort_order)

    @mcp.tool()
    def list_sections(slug: str) -> list[dict[str, Any]]:
        """List all sections for a paper."""
        return _sections.list_sections(state, slug)

    @mcp.tool()
    def get_manuscript(slug: str) -> str:
        """Return the assembled manuscript.md as a string."""
        return _sections.get_manuscript(state, slug)

    # ─── reviews / comments ──────────────────────────────────────────────────
    @mcp.tool()
    def add_review(
        slug: str,
        comment: str,
        source: str = "user",
        reviewer_name: str = "User",
        section: str | None = None,
        severity: str = "minor",
        manuscript_ref: str | None = None,
        anchor_text: str | None = None,
        anchor_prefix: str | None = None,
        anchor_suffix: str | None = None,
        anchor_occurrence: int | None = None,
        manuscript_snapshot: str | None = None,
        round: int | None = None,
    ) -> dict[str, Any]:
        """Create a new review/comment. Use source='user' for dashboard comments.

        For REAL journal reviewer points (a decision letter), use
        source='reviewer' with reviewer_name="Reviewer 1" etc. and `round`
        (submission round) — these are the only comments /response-letter builds
        from. source='ai' is internal self-review (/paper-review) and is never
        in a response letter.

        anchor_prefix/anchor_suffix are the text just before/after anchor_text;
        when anchor_text repeats in a section they let the dashboard highlight
        the exact occurrence instead of every match. anchor_occurrence is the
        0-based index of the intended instance among repeats (pins it exactly,
        even when the surrounding context is identical)."""
        return _reviews.add_review(
            state, slug, comment=comment, source=source, reviewer_name=reviewer_name,
            section=section, severity=severity, manuscript_ref=manuscript_ref,
            anchor_text=anchor_text, anchor_prefix=anchor_prefix,
            anchor_suffix=anchor_suffix, anchor_occurrence=anchor_occurrence,
            manuscript_snapshot=manuscript_snapshot, round=round,
        )

    @mcp.tool()
    def list_reviews(
        slug: str,
        status: str | None = None,
        source: str | None = None,
        decision: str | None = None,
        reviewer_name: str | None = None,
        round: int | None = None,
    ) -> list[dict[str, Any]]:
        """List reviews for a paper, optionally filtered by status, source, and/
        or the user's triage `decision` ('pending'|'accepted'|'rejected'). The
        author triages comments in the dashboard; `decision='accepted'` is the
        set they've approved you to act on (no decision == 'pending').

        `reviewer_name` + `round` isolate ONE reviewer's material — required when
        assembling a per-seat bundle for /reviewer-frame-check, since a merged
        run cannot surface a premise that only one reviewer is missing."""
        return _reviews.list_reviews(
            state, slug, status=status, source=source, decision=decision,
            reviewer_name=reviewer_name, round=round)

    @mcp.tool()
    def update_review(
        slug: str,
        review_id: str,
        status: str | None = None,
        response: str | None = None,
        decision: str | None = None,
        section: str | None = None,
        anchor_text: str | None = None,
        anchor_prefix: str | None = None,
        anchor_suffix: str | None = None,
        anchor_occurrence: int | None = None,
        anchors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Update a review's status / response, its triage `decision`, or
        correct where it points.

        `decision` ('pending'|'accepted'|'rejected') is normally set by the
        author in the dashboard — only set it from here if they tell you to.
        Pass `section` / `anchor_*` to fix a mis-anchored comment (wrong
        section, or a sentence that moved); for bulk section repair after edits
        use reconcile_review_anchors instead. Pass `anchors` (a list of verbatim
        passages) when one comment was addressed in several spots — each gets
        its own highlight/jump and the first becomes the primary anchor_text.
        Args left None are unchanged."""
        return _reviews.update_review(
            state, slug, review_id, status=status, response=response,
            decision=decision, section=section, anchor_text=anchor_text,
            anchor_prefix=anchor_prefix, anchor_suffix=anchor_suffix,
            anchor_occurrence=anchor_occurrence, anchors=anchors,
        )

    @mcp.tool()
    def delete_paper_comment(slug: str, review_id: str) -> bool:
        """Permanently delete a comment. Use to retract a wrong/obsolete AI
        reviewer ('ai') note — there is otherwise no way to remove one."""
        return _reviews.delete_review(state, slug, review_id)

    @mcp.tool()
    def reconcile_review_anchors(slug: str, dry_run: bool = True) -> dict[str, Any]:
        """Re-align open comments' stored `section` with where their anchor
        text actually lives now — fixes highlights that broke because a comment
        was stamped with the wrong section (or a title instead of a key), or
        the manuscript was edited. Run after import_paper, bulk section edits,
        or /paper-revision.

        dry_run=True (default) previews; dry_run=False applies. Returns
        {relocated, ok, truly_missing}. `truly_missing` = text no longer in any
        section (genuinely edited away) — left untouched for you to review."""
        return _reviews.reconcile_review_anchors(state, slug, dry_run=dry_run)

    @mcp.tool()
    def review_triage_summary(slug: str) -> dict[str, Any]:
        """One-call snapshot of comment triage for the submission gate / a
        session-start "what's left" check. Returns counts of accepted,
        accepted_unresolved (approved but not yet in the manuscript), rejected,
        rejected_without_rationale (rejected but no rebuttal in `response` —
        the response letter needs one), and pending, plus the offending
        review_ids. Address rejected_without_rationale with /paper-revision
        before exporting."""
        return _reviews.review_triage_summary(state, slug)

    @mcp.tool()
    def count_open_user_comments(slug: str, deck_id: str | None = None) -> int:
        """How many unresolved human comments exist — dashboard ('user') AND
        shared/public-page ('external') feedback, excluding AI reviewer notes.
        Counts BOTH manuscript review comments AND deck slide comments (all of
        the paper's decks, or just `deck_id` if given). Used for the
        SessionStart banner."""
        return _reviews.count_open_user_comments(state, slug, deck_id)

    @mcp.tool()
    def list_paper_comments(
        slug: str,
        status: str | None = "open",
        source: str | None = None,
        decision: str | None = None,
    ) -> list[dict[str, Any]]:
        """Full text of comments on a paper — dashboard ('user') and shared/
        public-page ('external') feedback, plus AI reviewer ('ai') notes. Each
        item carries section, anchor_text, reviewer_name, source, severity,
        comment, status, and the author's triage `decision`.

        status='open' (default) is the agent's revision to-do list; pass None
        for all. Optionally filter by source ('user'|'external'|'ai') or by
        `decision` ('accepted' = the author approved you to act on it; 'pending'
        = not yet triaged; 'rejected' = declined — skip it). When the author has
        triaged, prefer decision='accepted' as your work list. Read these,
        revise the manuscript, then resolve_paper_comment — the manuscript
        analogue of the list_deck_comments / resolve_deck_comment loop.
        """
        return _reviews.list_reviews(
            state, slug, status=status, source=source, decision=decision)

    @mcp.tool()
    def resolve_paper_comment(
        slug: str,
        review_id: str,
        status: str = "resolved",
        response: str | None = None,
        new_anchor_text: str | None = None,
        new_section: str | None = None,
        new_anchor_texts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Close a paper comment once addressed: status 'resolved' (done),
        'accepted' / 'rejected', or 'open' to reopen. Optionally attach a
        `response`. The manuscript analogue of resolve_deck_comment.

        IMPORTANT — re-anchor when you edited the text. If addressing the
        comment changed the sentence it was anchored to, the old anchor no
        longer matches and the dashboard can't point at the revised passage.
        Pass `new_anchor_text` = a verbatim phrase from the REVISED text (and
        `new_section` if it moved to another section) so the highlight follows
        to the new location.

        If you addressed the comment in SEVERAL places, pass `new_anchor_texts`
        = a list of one verbatim phrase per edited spot; the dashboard then
        highlights each and lets the reviewer cycle through them. Use rendered
        wording (no markdown markers), distinctive ~5–15 word spans."""
        return _reviews.update_review(
            state, slug, review_id, status=status, response=response,
            anchor_text=new_anchor_text, section=new_section,
            anchors=new_anchor_texts,
        )

    # ─── figures ─────────────────────────────────────────────────────────────
    @mcp.tool()
    def add_figure(
        slug: str,
        figure_number: int,
        title: str,
        caption: str | None = None,
        legend: str | None = None,
        local_path: str | None = None,
        source_analysis: str | None = None,
    ) -> dict[str, Any]:
        """Register a figure. If local_path provided, uploads image bytes to Storage.

        OMIT `local_path` to create a PLACEHOLDER — a numbered figure with a
        caption and no image yet. In the dashboard the body's `![](figure:N)`
        then renders as a drop zone the author fills by clicking, dropping or
        pasting a file, with no agent session in the loop. That is the right
        shape for a manual or a report where the text is written first and the
        screenshots are taken later: register every slot with the caption saying
        what to capture, and the person holding the screenshots fills them in.
        prepare_export warns about any still unfilled, since an image-less figure
        is dropped from the exported document.

        `source_analysis` names the analysis this artifact is generated from; set it so prepare_export can warn when that analysis re-runs and leaves this artifact stale.

        `caption` and `legend` describe what the item SHOWS: panels, axes,
        units, sample sizes, normalisation, and how to read the symbols.
        Interpretation stays OUT — what the result means, what it excludes,
        why it matters, and how it relates to other evidence belong to the
        body section that cites the item. A caption that argues duplicates
        the body, and the two copies then drift apart under revision.
        The split between the two fields: `caption` is the 'Figure N.'
        sentence plus what is depicted; `legend` is panel-by-panel and
        symbol-level detail. Journals print them as one block.
        lint_legends flags a caption that has grown into a mini-Results."""
        return _figures.add_figure(
            state, slug, figure_number=figure_number, title=title,
            caption=caption, legend=legend, local_path=local_path,
            source_analysis=source_analysis,
        )

    @mcp.tool()
    def add_figure_panel(
        slug: str,
        figure_number: int,
        local_path: str,
        label: str | None = None,
        caption: str | None = None,
    ) -> dict[str, Any]:
        """Add one image to a figure as a labelled panel, and RECOMPOSE.

        Panels are the editable source list; every change composes them into a
        single image at the figure's `blob_path` — one column, equal widths, an
        (A)/(B)/(C) label per panel. That is what makes it correct downstream: a
        journal wants one composed figure per number, and neither pandoc nor
        python-docx can compose, so exporting stacked panels would be wrong in a
        way you would only find at submission.

        `label` defaults to the next free letter. An existing single image becomes
        panel A, so adding a second panel never loses the first."""
        return _figures.add_figure_panel(
            state, slug, figure_number, local_path=local_path, label=label,
            caption=caption)

    @mcp.tool()
    def compose_figure_panels(slug: str,
                              figure_number: int | None = None) -> dict[str, Any]:
        """Rebuild the composite for figures whose panels changed.

        The dashboard can upload panels but cannot compose them (no Python), so
        panels added there wait for this. Leave `figure_number` off to catch up on
        every figure at once — that batching is the reason deferring is
        acceptable. prepare_export warns while any are outstanding, because until
        then the document still carries the PREVIOUS image while the author
        believes the panels are in."""
        return _figures.compose_figure_panels(state, slug, figure_number)

    @mcp.tool()
    def delete_figure_panel(slug: str, figure_number: int,
                            panel_id: str) -> dict[str, Any]:
        """Remove one panel and recompose the rest. Removing the last one leaves
        the figure empty again, which prepare_export then warns about."""
        return _figures.delete_figure_panel(state, slug, figure_number, panel_id)

    @mcp.tool()
    def update_figure(
        slug: str,
        figure_number: int,
        title: str | None = None,
        caption: str | None = None,
        legend: str | None = None,
        local_path: str | None = None,
        status: str | None = None,
        source_analysis: str | None = None,
        prompt: str | None = None,
    ) -> dict[str, Any]:
        """Patch a figure; optionally replace the image bytes.

        `source_analysis` names the analysis this artifact is generated from; set it so prepare_export can warn when that analysis re-runs and leaves this artifact stale.

        Replacing the bytes (`local_path`) WITHOUT passing a `prompt` retires the
        stored generation prompt to `prompt_superseded`. Supplying bytes says the
        image is no longer what the prompt described, and a surviving prompt lets
        a dashboard re-render silently replace a hand-built figure with an AI
        raster drawn from stale text. `prompt=""` clears it explicitly; a plain
        metadata edit leaves it alone.

        `caption`/`legend` describe what the item SHOWS: panels, axes, units,
        sample sizes, normalisation, how to read the symbols. Interpretation
        stays OUT — what the result means, what it excludes, why it matters
        belong to the body section that cites the item. A caption that argues
        duplicates the body, and the two copies drift apart under revision.
        `caption` = the 'Figure N.' sentence plus what is depicted; `legend` =
        panel-by-panel and symbol detail. lint_legends flags a caption that
        has grown into a mini-Results."""
        return _figures.update_figure(
            state, slug, figure_number, title=title, caption=caption,
            legend=legend, local_path=local_path, status=status,
            source_analysis=source_analysis, prompt=prompt,
        )

    @mcp.tool()
    def get_figure(
        slug: str,
        figure_number: int,
        dest_dir: str | None = None,
        dest_path: str | None = None,
    ) -> dict[str, Any]:
        """Figure metadata. Pass dest_dir or dest_path to also download the
        image blob locally (adds `local_path` to the result) — e.g. to embed
        the PNG in a docx or hand it to the user."""
        return _figures.get_figure(
            state, slug, figure_number, dest_dir=dest_dir, dest_path=dest_path,
        )

    @mcp.tool()
    def list_figures(slug: str, supplementary: bool | None = False) -> list[dict[str, Any]]:
        """List figures. supplementary=False → main only (default), True → SFigures
        only, None → all (main + supplementary)."""
        return _figures.list_figures(state, slug, supplementary=supplementary)

    @mcp.tool()
    def lint_figure_layout(
        nodes: list[dict[str, Any]],
        canvas_w: float,
        canvas_h: float,
        edges: list[dict[str, Any]] | None = None,
        min_gap: float = 0.0,
        figure_w_in: float | None = None,
        figure_h_in: float | None = None,
    ) -> dict[str, Any]:
        """Deterministically lint a CODE-figure layout spec BEFORE rendering —
        turns the slow render-and-eyeball loop into a fast geometric one.

        nodes: [{id, x, y, w, h, label?, font_size?, padding?, wrap?}] where
        (x,y) is the box bottom-left corner, y-up, on a [0,canvas_w] x
        [0,canvas_h] canvas. edges: [{src, dst, src_side?, dst_side?}] with sides
        center|top|bottom|left|right. Returns {ok, issues, counts} covering
        box_overlap (respecting min_gap), out_of_canvas, arrow_crosses_box (an
        edge passing through an unrelated node — the check a visual review
        misses), and **label_overflow** (a node's text doesn't fit its box).
        For label_overflow, give each box a `label` + `font_size` (pt) and pass
        `figure_w_in`/`figure_h_in` (figure size in inches, needed to map the
        box's DATA units to text POINTS). It reports measured vs available size,
        a suggested max font, and a min box; the extent is a CJK-aware estimate,
        so treat borderline hits as "confirm at render"."""
        return _figure_lint.lint_layout(
            nodes, edges, canvas_w=canvas_w, canvas_h=canvas_h, min_gap=min_gap,
            figure_w_in=figure_w_in, figure_h_in=figure_h_in)

    @mcp.tool()
    def delete_figure(slug: str, figure_number: int) -> dict[str, Any]:
        return {"deleted": _figures.delete_figure(state, slug, figure_number)}

    # ─── reference materials (project-level user-uploaded source files) ──────
    @mcp.tool()
    def list_materials() -> list[dict[str, Any]]:
        """List the project's reference materials — source files the user
        uploaded in the dashboard for you to consult while working (PDFs to
        read, datasets to analyze, prior drafts, notes, images). Shared
        across the whole project, not tied to one paper. Distinct from
        `references` (cited works): a material is a FILE, a reference is a
        CITATION. Each entry has {material_id, filename, content_type,
        size_bytes, description}. Call at session start to see what the user
        wants you to work from, then `get_material` to pull the file.
        """
        return _materials.list_materials(state)

    @mcp.tool()
    def get_material(
        material_id: str,
        dest_dir: str = ".",
        dest_path: str | None = None,
    ) -> dict[str, Any]:
        """Download a reference material to local disk so you can open it.
        Writes to `dest_path` if given, else `dest_dir`/<original-filename>.
        Returns {path, filename, size_bytes, content_type}. After this,
        read the file from the returned path with your normal file tools.
        """
        return _materials.get_material(
            state, material_id, dest_dir=dest_dir, dest_path=dest_path,
        )

    @mcp.tool()
    def add_material(
        local_path: str,
        ai_note: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Upload a local file as a project reference material, so it also
        appears in the dashboard's Materials tab. Use when YOU produce a
        source file the user should see. For files the user uploaded, use
        list_materials/get_material instead.

        `ai_note` is YOUR metadata about the file (what it is, key columns, how
        it's relevant). NEVER write the user's note — `user_note` is the user's
        own field, editable only from the dashboard. (`description` is a legacy
        alias for `ai_note`.)
        """
        return _materials.add_material(
            state, local_path=local_path, ai_note=ai_note, description=description,
        )

    @mcp.tool()
    def update_material(material_id: str, ai_note: str) -> dict[str, Any]:
        """Set/replace YOUR metadata note (`ai_note`) on a material — works on
        any material, including ones the user uploaded (read them with
        list_materials, then annotate what each file is). This only touches
        `ai_note`; the user's `user_note` is left alone, so you can't overwrite
        what the user wrote."""
        return _materials.update_material(state, material_id, ai_note=ai_note)

    @mcp.tool()
    def delete_material(material_id: str) -> dict[str, Any]:
        return {"deleted": _materials.delete_material(state, material_id)}

    # ─── other projects (READ-ONLY reference across your own account) ───────
    @mcp.tool()
    def list_my_projects() -> list[dict[str, Any]]:
        """Every project this account owns, with the active one first.

        Use when the user refers to work in another project ("like we did in
        the rice paper"). Everything else in this group needs a project_id from
        here."""
        return _cross.list_my_projects(state)

    @mcp.tool()
    def search_my_papers(query: str) -> list[dict[str, Any]]:
        """Find papers across ALL your projects by title/slug/journal substring.

        The lookup for "I wrote this somewhere but I forget where" — it answers
        WHICH project, which every other cross-project tool assumes you know."""
        return _cross.search_my_papers(state, query)

    @mcp.tool()
    def list_project_papers(project_id: str) -> list[dict[str, Any]]:
        """Papers in another of your projects (slug, title, type, status)."""
        return _cross.list_project_papers(state, project_id)

    @mcp.tool()
    def read_project_paper(
        project_id: str, slug: str, section_key: str = "",
    ) -> dict[str, Any]:
        """Read a paper from another of YOUR projects, for reference.

        READ-ONLY: this session can only write to its own project, and a write
        through this view raises rather than silently doing nothing. To reuse
        something, read it here and WRITE it with the normal tools — then it
        lands in the active project's activity log, where it belongs.

        Pass `section_key` (e.g. "methods") for one section. Prefer that: a
        Methods paragraph you are adapting is usually all you want, and the
        whole manuscript is a lot of context to spend to get it."""
        return _cross.read_project_paper(
            state, project_id, slug, section_key=section_key or None)

    @mcp.tool()
    def read_project_memory(project_id: str) -> dict[str, Any]:
        """Another of your projects' memory document — its working notes. Often
        the fastest way to recall how a decision was made over there."""
        return _cross.read_project_memory(state, project_id)

    @mcp.tool()
    def list_project_materials(project_id: str) -> list[dict[str, Any]]:
        """Materials in another of your projects. Fetch with
        get_project_material."""
        return _cross.list_project_materials(state, project_id)

    @mcp.tool()
    def get_project_material(
        project_id: str, material_id: str,
        dest_dir: str = ".", dest_path: str | None = None,
    ) -> dict[str, Any]:
        """Download a material from another of your projects to local disk.
        The cloud side stays read-only; your working directory does not."""
        return _cross.get_project_material(
            state, project_id, material_id, dest_dir=dest_dir, dest_path=dest_path)

    # ─── the submitted baseline (what the journal actually received) ────────
    @mcp.tool()
    def list_submissions(slug: str) -> list[dict[str, Any]]:
        """What was SENT for this paper, most recent first — the first entry is
        the current baseline.

        **Read this before /tracked-changes-export or /reviewer-frame-check.**
        Those two need the document the reviewers hold, and it is not the
        current manuscript and not the newest export. If this is empty, ASK the
        user which file was sent rather than substituting anything — that
        substitution silently defeats both skills and produces a marked-up copy
        that diffs against a document nobody read."""
        return _submissions.list_submissions(state, slug)

    @mcp.tool()
    def get_submission(
        slug: str,
        submission_id: str | None = None,
        dest_dir: str = ".",
        dest_path: str | None = None,
    ) -> dict[str, Any]:
        """Download a submitted file (latest if no id). The checksum recorded at
        registration is re-verified, so the copy can be trusted without being
        re-read."""
        return _submissions.get_submission(
            state, slug, submission_id, dest_dir=dest_dir, dest_path=dest_path)

    @mcp.tool()
    def register_submission(
        slug: str,
        export_id: str | None = None,
        local_path: str | None = None,
        venue: str | None = None,
        submitted_on: str | None = None,
        label: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Archive the file the journal received. Give exactly one of
        `export_id` or `local_path`.

        **Only when the USER has told you WHICH FILE it was. Never infer that**
        from filenames or dates — the newest export sorts first and looks the
        most authoritative, and that is exactly the trap.

        `venue` defaults to the paper's registered journal and `submitted_on` to
        today; pass them only to override. Those two are not worth asking about:
        the journal is already recorded, and a submission is normally registered
        when it is sent.

        Prefer `local_path` when the user edited the export before sending it,
        which is the ordinary case. The bytes are copied, so a later export
        cannot change what this says was submitted, and a sha256 is recorded so
        the copy can be proven to be the copy.

        Registering is normally the user's own act from the dashboard's Exports
        card; this tool is for when they ask you to do it."""
        return _submissions.register_submission(
            state, slug, venue=venue, submitted_on=submitted_on,
            export_id=export_id, local_path=local_path, label=label, note=note)

    @mcp.tool()
    def diff_submission(
        slug: str, submission_id: str | None = None,
    ) -> dict[str, Any]:
        """Compare this project's sections against the file that was SENT.

        Read-only. **Run it when `get_paper_state(slug)["paper"]
        ["submission_sync"]["state"]` is `unreconciled`, and before any revision
        work** — the sent file is usually the one the user hand-edited on its
        way out, so the sections are not what the reviewers hold, and a revision
        written on them starts from a document that exists nowhere.

        Read `missing_from_sections` first: those are the paragraphs the journal
        has and this project does not. Show them to the user and ASK before
        writing anything — which differences were deliberate is theirs to say,
        not yours to infer. Apply what they confirm with `update_section`, then
        call `acknowledge_submission_sync`."""
        return _submissions.diff_submission(state, slug, submission_id)

    @mcp.tool()
    def acknowledge_submission_sync(
        slug: str, note: str | None = None,
    ) -> dict[str, Any]:
        """Mark the sections reconciled with the submitted file, so the question
        stops being raised. Call it after the differences have been applied — or
        looked at with the user and deliberately left, with `note` saying why.
        Clearing it without looking is worse than never having asked."""
        return _submissions.acknowledge_submission_sync(state, slug, note=note)

    @mcp.tool()
    def delete_submission(slug: str, submission_id: str) -> dict[str, Any]:
        """Remove a registration made in error — the only way to change one.
        There is no edit: a submission that could be amended would stop being a
        record of what was sent."""
        return {"deleted": _submissions.delete_submission(state, slug, submission_id)}

    # ─── study documents (explainers, read inline in the dashboard) ─────────
    @mcp.tool()
    def write_study(
        title: str,
        html: str,
        summary: str | None = None,
        status: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        follows: str | None = None,
    ) -> dict[str, Any]:
        """Publish an explainer that READS INLINE in the dashboard's Study tab.

        Use this, not `add_material`, for a document written to be read. A
        material is what the paper REFERS to; a study is what a person reads,
        and filing an explainer as a material means it can only be opened by
        downloading it.

        `summary` is for the READER — a sentence or two saying what this
        explains, shown in the list. Your own caveats and reasoning belong in a
        material's `ai_note`; keeping them apart is why both exist.

        `sources` is WHERE THE NUMBERS CAME FROM:
        `[{"kind": "analysis", "ref": "mlm-eval", "label": "bits/bp"}]`
        (kinds: analysis, decision, graph, paper, run). Recording one stamps
        "read now"; when that source next changes the document shows as out of
        date on its own. Set this whenever the document contains a measured
        value — it is the difference between noticing a stale table and quoting
        it.

        `status` is `confirmed` or `provisional`. There is no `stale` status:
        staleness is computed from `sources`, because a flag someone has to
        remember to set is the same memory that already failed.

        `follows` is the study this one continues; the tab lists a series in
        reading order.
        """
        return _studies.write_study(
            state, title=title, html=html, summary=summary, status=status,
            sources=sources, follows=follows)

    @mcp.tool()
    def update_study(
        study_id: str,
        html: str | None = None,
        title: str | None = None,
        summary: str | None = None,
        status: str | None = None,
        sources: list[dict[str, Any]] | None = None,
        follows: str | None = None,
    ) -> dict[str, Any]:
        """Amend a study. Passing `html` replaces the document AND re-stamps its
        sources as read now — rewriting the tables is what makes them current,
        so the document should not stay flagged afterwards."""
        return _studies.update_study(
            state, study_id, html=html, title=title, summary=summary,
            status=status, sources=sources, follows=follows)

    @mcp.tool()
    def list_studies() -> list[dict[str, Any]]:
        """Every study, each with `stale` and which source moved.

        **Read this before quoting a number out of one of these documents.**
        `stale` means a source has changed since the document last read it, so
        the tables in it may no longer say what the analysis says.

        `decisions_since` is a DIFFERENT and weaker signal: decisions recorded
        after the document was written that it does not cite. Often irrelevant,
        never a verdict — but it is the only thing that catches "the numbers are
        still right and the interpretation reversed", which no citation-tracking
        can see. Judge it; do not treat it as staleness."""
        return _studies.list_studies(state)

    @mcp.tool()
    def read_study(study_id: str) -> dict[str, Any]:
        """One study's metadata and its HTML."""
        return _studies.read_study(state, study_id)

    @mcp.tool()
    def delete_study(study_id: str) -> dict[str, Any]:
        return {"deleted": _studies.delete_study(state, study_id)}

    # ─── published pages (unlisted URL, optional per-person passcodes) ──────
    @mcp.tool()
    def publish_page(
        title: str,
        html: str | None = None,
        material_id: str | None = None,
        require_passcode: bool = True,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Publish a page at an UNLISTED url, for people with no Scivo account.

        Give exactly one of `html` (the page source) or `material_id` (an HTML
        material already uploaded). Returns the url.

        The page runs in the dashboard's origin and is handed a scoped
        `window.scivo` client — see the guide. It can read anything under its
        own publication and write responses, and it can reach NOTHING else in
        the project.

        `require_passcode` defaults True. Issue one code per person with
        `add_passcode(label=...)`: the label rides in their token and the rules
        require every response to carry it, so two reviewers can never be
        confused for each other and neither can write as the other. A page with
        NO passcode can read but not write — an unattributable response is not
        evidence of anything, so it is refused rather than merged into one
        anonymous bucket."""
        return _publications.publish_page(
            state, title=title, html=html, material_id=material_id,
            require_passcode=require_passcode, description=description)

    @mcp.tool()
    def update_publication(
        pub_id: str,
        html: str | None = None,
        title: str | None = None,
        active: bool | None = None,
        require_passcode: bool | None = None,
    ) -> dict[str, Any]:
        """Amend a published page. `active=False` UNPUBLISHES it — checked when
        a visitor's token is minted, so it stops the next visitor even though
        links already sent out cannot be recalled."""
        return _publications.update_publication(
            state, pub_id, html=html, title=title, active=active,
            require_passcode=require_passcode)

    @mcp.tool()
    def list_publications() -> list[dict[str, Any]]:
        """Every published page in this project, with its url and whether it is
        still live."""
        return _publications.list_publications(state)

    @mcp.tool()
    def add_passcode(pub_id: str, label: str) -> dict[str, Any]:
        """Issue a passcode for ONE person.

        `label` is how their responses are attributed — a name or a role. Give
        each collaborator their own: which code opened the link is the only
        record of who did the work, and the label is enforced on every write.

        The code stays readable via `list_passcodes`, so it can be re-sent to
        someone who mislaid it. A page visitor cannot read it — the rules refuse
        the `passcodes` collection outright."""
        return _publications.add_passcode(state, pub_id, label=label)

    @mcp.tool()
    def list_passcodes(pub_id: str) -> list[dict[str, Any]]:
        """Issued passcodes — label, the code, whether active, and how often
        used. Owner-side only; the published page cannot read this."""
        return _publications.list_passcodes(state, pub_id)

    @mcp.tool()
    def revoke_passcode(pub_id: str, code_id: str) -> dict[str, Any]:
        """Deactivate one passcode. Responses it already produced are KEPT —
        the person stops getting in; what they already judged is evidence."""
        return _publications.revoke_passcode(state, pub_id, code_id)

    @mcp.tool()
    def put_page_data(
        pub_id: str, collection: str, doc_id: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Write a document the published page will READ — the items to review,
        its config, whatever it needs. Use collection "items" or "content".

        Anything under a publication is published; that is the whole rule, and
        it is why the page's data goes here rather than being granted piecemeal
        out of the project."""
        return _publications.put_page_data(
            state, pub_id, collection=collection, doc_id=doc_id, data=data)

    @mcp.tool()
    def list_responses(pub_id: str, collection: str = "responses") -> list[dict[str, Any]]:
        """What the published page wrote back. Each response carries the
        `reviewer` label of the passcode that produced it, enforced at write
        time — so independent judgements can be split apart and compared
        without trusting anything the page said about itself."""
        return _publications.list_responses(state, pub_id, collection=collection)

    # ─── discussion: comments on a graph, and the decisions that came out ───
    @mcp.tool()
    def list_decisions(include_superseded: bool = False) -> list[dict[str, Any]]:
        """Decisions this project has already settled, newest first.

        READ THIS AT SESSION START, with the project memory. It is the standing
        record of what has been argued and closed — re-opening a settled
        question is the most expensive thing you can do here, and proposing
        something already rejected is worse than proposing nothing.

        `include_superseded=True` adds reversed decisions, each carrying
        `superseded_by` so you can see WHAT replaced it."""
        return _discussion.list_decisions(
            state, include_superseded=include_superseded)

    @mcp.tool()
    def record_decision(
        text: str,
        rationale: str | None = None,
        from_graph: str | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Write down what the discussion decided, so it appears on the
        Discussion tab's bulletin.

        Record a decision when the USER settles something, not when you form an
        opinion — this is the project's record, not your notes; project memory
        is where your own reading belongs.

        `rationale` is the line worth having in a year: the text says WHAT was
        decided, the rationale says why the alternatives lost. `from_graph` is
        the graph material_id being discussed. `supersedes` reverses an earlier
        decision — the old one is kept and marked, never deleted, and every
        study that CITED it goes out of date automatically.

        The reply carries `studies_to_review`: explainers that now cite
        something that moved, or that were written before decisions you have
        since recorded. **Read it.** A study's tables can stay perfectly correct
        while the way to read them reverses, and that is the failure this
        surfaces at the one moment someone can act on it."""
        return _discussion.record_decision(
            state, text=text, rationale=rationale, from_graph=from_graph,
            supersedes=supersedes)

    @mcp.tool()
    def list_discussion(graph_id: str = "") -> list[dict[str, Any]]:
        """Comments on the drawn graphs, oldest first. Pass `graph_id` for one
        graph's thread. Read the graph itself with read_graph."""
        return _discussion.list_discussion(state, graph_id or None)

    @mcp.tool()
    def post_comment(
        graph_id: str, body: str, parent_id: str | None = None,
    ) -> dict[str, Any]:
        """Say something in a graph's discussion thread, or reply to a comment.

        You are a participant here, and it is marked as such — everything you
        post is attributed to the agent, so a reader can always tell which
        arguments in the record were yours."""
        return _discussion.post_comment(
            state, graph_id=graph_id, body=body, parent_id=parent_id)

    # ─── graphs (node-edge-node diagrams, stored as .graph.json materials) ───
    @mcp.tool()
    def list_graphs() -> list[dict[str, Any]]:
        """List the project's node-edge-node graphs — the diagrams the user
        draws in the dashboard's Discussion tab, and the ones you write there.

        Each carries `graph_kind` and, if a later revision took over,
        `superseded_by` — read THAT one instead, the old drawing is kept only so
        the revision stays followable. Cheap; read one with read_graph."""
        return _graphs.list_graphs(state)

    @mcp.tool()
    def read_graph(material_id: str) -> dict[str, Any]:
        """Read a graph as DATA: nodes (with `incoming`/`outgoing` adjacency),
        edges, labels, kinds. Use this when the user says "the graph I drew" —
        it is a workflow/model you can turn into a methods paragraph, a
        pipeline, or a figure, not a picture."""
        return _graphs.read_graph(state, material_id)

    @mcp.tool()
    def write_graph(
        title: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]] | None = None,
        ai_note: str | None = None,
        graph_kind: str | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Draw a NEW graph for the user, visible and editable in the
        Discussion tab. Good for making an analysis flow, a sample/cross design, or a
        pathway concrete enough to correct.

        `nodes`: [{"label": "Raw reads", "kind": "input", "shape": "cylinder"},
        ...] — `label` is all that's required. `kind` is free text ("input",
        "step", ...). `shape` carries the node's ROLE and a reader takes that
        meaning whether or not you meant it, so pick deliberately:

          box (default) a process or action      round      entry / terminal
          diamond       a branch — the edges out are its outcomes
          cylinder      a dataset, file or store
          parallelogram material in, or a result out
          hexagon       setup, sampling or preparation

        `edges`: [{"from": "Raw reads", "to": "Trimming", "label": "fastq.gz"}]
        — endpoints may be node labels or ids. An edge label is drawn ON the
        line, in a break in it, so name what MOVES along the edge (a format, a
        count, a condition), not the step it arrives at.

        `graph_kind` says what the drawing IS, and the Discussion tab groups by
        it: `structure` (how parts connect), `measurement` (where numbers come
        from and what they are now), `plan` (branch points and outputs),
        `concept` (a model being worked out), `other`. They update on different
        rhythms — a structure when the design changes, a measurement map with
        every result — so a flat list hides which one is due for a look.

        `supersedes` marks this as the REVISION of an earlier graph, the same
        way `record_decision(supersedes=…)` does. The old drawing is kept and
        marked rather than deleted, so v1 stays followable from v2. Use it for a
        new version of the SAME drawing; a different drawing is just a new
        graph.

        Positions are laid out for you; the user rearranges them and that
        arrangement is then preserved.
        """
        return _graphs.write_graph(
            state, title=title, nodes=nodes, edges=edges, ai_note=ai_note,
            graph_kind=graph_kind, supersedes=supersedes,
        )

    @mcp.tool()
    def edit_graph(
        material_id: str,
        title: str | None = None,
        add_nodes: list[dict[str, Any]] | None = None,
        rename_nodes: dict[str, Any] | None = None,
        remove_nodes: list[str] | None = None,
        add_edges: list[dict[str, Any]] | None = None,
        remove_edges: list[dict[str, Any]] | None = None,
        ai_note: str | None = None,
        graph_kind: str | None = None,
    ) -> dict[str, Any]:
        """Amend an existing graph. Anything you don't mention is left exactly
        as it is — including where the user dragged each box, which is why you
        should edit rather than rewrite a graph the user has touched.

        `rename_nodes`: {"trimming": "Trimming (fastp)"} or
        {"trimming": {"label": "...", "kind": "step", "shape": "diamond"}}.
        `remove_edges`: [{"from": "a", "to": "b"}] or [{"id": "e1234abcd"}].
        Removing a node removes its edges too.
        """
        return _graphs.edit_graph(
            state, material_id, title=title, add_nodes=add_nodes,
            rename_nodes=rename_nodes, remove_nodes=remove_nodes,
            add_edges=add_edges, remove_edges=remove_edges, ai_note=ai_note,
            graph_kind=graph_kind,
        )

    # ─── tables ──────────────────────────────────────────────────────────────
    @mcp.tool()
    def add_table(
        slug: str,
        table_number: int,
        title: str,
        content: str,
        caption: str | None = None,
        source_analysis: str | None = None,
    ) -> dict[str, Any]:
        """Register a table. `source_analysis` names the analysis this artifact is generated from; set it so prepare_export can warn when that analysis re-runs and leaves this artifact stale.

        `caption`/`legend` describe what the item SHOWS: columns, units, sample
        sizes, normalisation, how to read the symbols. Interpretation
        stays OUT — what the result means, what it excludes, why it matters
        belong to the body section that cites the item. A caption that argues
        duplicates the body, and the two copies drift apart under revision.
        `caption` = the 'Table N.' sentence plus what is depicted; `legend` =
        column definitions and footnotes. lint_legends flags a caption that
        has grown into a mini-Results."""
        return _tables.add_table(
            state, slug, table_number=table_number, title=title,
            content=content, caption=caption, source_analysis=source_analysis,
        )

    @mcp.tool()
    def update_table(
        slug: str,
        table_number: int,
        title: str | None = None,
        content: str | None = None,
        caption: str | None = None,
        status: str | None = None,
        source_analysis: str | None = None,
    ) -> dict[str, Any]:
        """Patch a table. `source_analysis` names the analysis this artifact is generated from; set it so prepare_export can warn when that analysis re-runs and leaves this artifact stale.

        `caption`/`legend` describe what the item SHOWS: columns, units, sample
        sizes, normalisation, how to read the symbols. Interpretation
        stays OUT — what the result means, what it excludes, why it matters
        belong to the body section that cites the item. A caption that argues
        duplicates the body, and the two copies drift apart under revision.
        `caption` = the 'Table N.' sentence plus what is depicted; `legend` =
        column definitions and footnotes. lint_legends flags a caption that
        has grown into a mini-Results."""
        return _tables.update_table(
            state, slug, table_number, title=title, content=content,
            caption=caption, status=status, source_analysis=source_analysis,
        )

    @mcp.tool()
    def get_table(slug: str, table_number: int) -> dict[str, Any]:
        return _tables.get_table(state, slug, table_number)

    @mcp.tool()
    def list_tables(slug: str, supplementary: bool | None = False) -> list[dict[str, Any]]:
        """List tables. supplementary=False → main only (default), True → STables
        only, None → all (main + supplementary)."""
        return _tables.list_tables(state, slug, supplementary=supplementary)

    @mcp.tool()
    def delete_table(slug: str, table_number: int) -> dict[str, Any]:
        return {"deleted": _tables.delete_table(state, slug, table_number)}

    @mcp.tool()
    def reorder_supplementary(slug: str, kind: str, order: list[int]) -> dict[str, Any]:
        """Renumber the supplementary figures or tables into a new order.

        kind: 'figure' or 'table'. order: the CURRENT supplementary numbers
        (≥101) in the desired new sequence; they are reassigned to 101,102,…
        accordingly. Moves the docs (and copies figure image blobs server-side —
        no re-upload), and auto-rewrites deterministic body refs ({fig:N}/{tab:N}
        tokens and ![](figure:N) embeds). Freeform prose mentions
        ("Supplementary Figure 1", "Fig. S2"…) are NOT rewritten — they're
        returned in `prose_mentions` so you can update them precisely. Returns
        {mapping, tokens_updated, embeds_updated, sections_changed,
        prose_mentions}."""
        return _reorder.reorder_supplementary(state, slug, kind, order)

    # ─── references ──────────────────────────────────────────────────────────
    @mcp.tool()
    def add_reference(
        slug: str,
        citation_key: str,
        title: str,
        authors: list[str] | None = None,
        journal: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        pmid: str | None = None,
        bibtex: str | None = None,
        volume: str | None = None,
        issue: str | None = None,
        pages: str | None = None,
        issn: str | None = None,
        publisher: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Register a reference by hand. Use add_reference_by_doi when a DOI
        exists — it fills every field from CrossRef. This is for works that
        predate DOI assignment or are absent from CrossRef.

        WHICH SOURCE WINS: if `bibtex` is set, the export emits it VERBATIM and
        ignores every structured field. So either paste a complete BibTeX entry
        and let it stand, or leave `bibtex` empty and fill the structured fields
        (volume/issue/pages/issn/publisher/url are all writable here) — a
        half-filled `bibtex` silently discards the rest, and the loss shows up
        only in the finished PDF.
        """
        return _references.add_reference(
            state, slug, citation_key=citation_key, title=title, authors=authors,
            journal=journal, year=year, doi=doi, pmid=pmid, bibtex=bibtex,
            volume=volume, issue=issue, pages=pages, issn=issn,
            publisher=publisher, url=url,
        )

    @mcp.tool()
    def update_reference(
        slug: str,
        citation_key: str,
        title: str | None = None,
        authors: list[str] | None = None,
        journal: str | None = None,
        year: int | None = None,
        doi: str | None = None,
        pmid: str | None = None,
        bibtex: str | None = None,
        volume: str | None = None,
        issue: str | None = None,
        pages: str | None = None,
        issn: str | None = None,
        publisher: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Amend a reference. Only the fields you pass are written.

        A set `bibtex` field wins over every structured field at export — see
        add_reference. To move a reference off a pasted BibTeX blob and onto
        structured fields, pass bibtex="" along with them.
        """
        return _references.update_reference(
            state, slug, citation_key, title=title, authors=authors,
            journal=journal, year=year, doi=doi, pmid=pmid, bibtex=bibtex,
            volume=volume, issue=issue, pages=pages, issn=issn,
            publisher=publisher, url=url,
        )

    @mcp.tool()
    def get_reference(slug: str, citation_key: str) -> dict[str, Any]:
        return _references.get_reference(state, slug, citation_key)

    @mcp.tool()
    def list_references(slug: str, cited_in: str = "") -> list[dict[str, Any]]:
        """List a paper's references. Pass `cited_in` (a short/figure id) to
        return only references tagged with it — e.g. to build a science short's
        reference card / description from exactly the works it cited."""
        return _references.list_references(state, slug, cited_in=cited_in or None)

    @mcp.tool()
    def search_references(
        slug: str,
        doi: str | None = None,
        pmid: str | None = None,
        year: int | None = None,
        title_contains: str | None = None,
    ) -> list[dict[str, Any]]:
        return _references.search_references(
            state, slug, doi=doi, pmid=pmid, year=year, title_contains=title_contains,
        )

    @mcp.tool()
    def delete_reference(slug: str, citation_key: str) -> dict[str, Any]:
        return {"deleted": _references.delete_reference(state, slug, citation_key)}

    # ─── DOI verification (CrossRef-backed) ──────────────────────────────────
    @mcp.tool()
    def search_works(
        query: str,
        limit: int = 10,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search CrossRef for works matching `query` (free-text topic).

        Returns up to `limit` (max 50) results each with title, authors,
        journal, year, subjects, abstract, DOI, and URL. Use BEFORE
        `add_reference_by_doi` so the agent can show candidates and let
        the user pick which to register.

        Optional year filters: `year_from`/`year_to` (inclusive).
        """
        return _references.search_works(
            state, query=query, limit=limit,
            year_from=year_from, year_to=year_to,
        )

    @mcp.tool()
    def verify_doi(doi: str) -> dict[str, Any]:
        """Resolve a DOI against CrossRef. Returns title/authors/journal/year
        if real, raises if CrossRef returns 404 (likely hallucinated DOI).

        Use BEFORE inserting a citation into a manuscript. No Firestore write.
        """
        return _references.verify_doi(state, doi)

    @mcp.tool()
    def add_reference_by_doi(
        slug: str,
        doi: str,
        citation_key: str | None = None,
        cited_in: list[str] | None = None,
    ) -> dict[str, Any]:
        """Fetch CrossRef metadata for `doi` and store as a reference.

        Auto-derives citation_key like 'smith2024' from first-author surname
        + year if not provided. Refuses to store DOIs CrossRef returns 404
        for — that's the primary hallucination guard.
        """
        return _references.add_reference_by_doi(
            state, slug, doi=doi, citation_key=citation_key, cited_in=cited_in,
        )

    @mcp.tool()
    def enrich_reference_from_doi(slug: str, citation_key: str) -> dict[str, Any]:
        """For an existing reference with only a DOI, fill in missing
        title/authors/journal/year + volume/issue/pages/issn/publisher from
        CrossRef. Won't overwrite existing non-empty fields.
        """
        return _references.enrich_reference_from_doi(state, slug, citation_key)

    @mcp.tool()
    def backfill_references(slug: str) -> dict[str, Any]:
        """One pass over ALL references: fetch CrossRef for each with a DOI and
        fill in any missing volume/issue/pages/issn/publisher (and
        title/authors/journal/year if blank). Use this to complete a
        bibliography whose exported citations end at the journal name with no
        volume:pages. Never overwrites non-empty fields. Returns a per-key
        summary (enriched / already_complete / no_doi / errors)."""
        return _references.backfill_references(state, slug)

    @mcp.tool()
    def set_reference_taxa(taxa: list[str]) -> dict[str, Any]:
        """Set the project's auto-italicize taxon list — genus + infrageneric
        names (subgenus/section) that the bibliography renderer italicizes in
        reference titles even when CrossRef didn't mark them up. Seed from the
        paper's study genera. Family-and-above (-aceae/-ales) is never
        italicized; matching is word-bounded. Empty list disables it."""
        return _references.set_reference_taxa(state, taxa)

    @mcp.tool()
    def get_reference_taxa() -> list[str]:
        """Return the project's auto-italicize taxon list (empty if unset)."""
        return _references.get_reference_taxa(state)

    @mcp.tool()
    def validate_references(slug: str) -> dict[str, Any]:
        """Gather facts the AGENT needs to judge every citation.

        The MCP does NOT decide whether a citation's context fits the
        cited paper — that's your job as the LLM. Word-overlap is too
        unreliable for that judgment. Server emits only deterministic
        categories:

          - unresolved: CrossRef returned 404 (almost certainly fake DOI)
          - missing_doi: reference has no DOI to check
          - errors: transient lookup failures

        Plus `results[]` — one entry per resolvable DOI, each carrying:

          - crossref: full metadata (title, abstract, subjects, authors,
            year, journal, type, url)
          - manuscript_contexts: every {doi:X} occurrence in section
            bodies with surrounding sentence + 240-char before/after +
            stacked_with (sibling DOIs in the same citation chunk)
          - signals: raw overlap counts. Use as a hint, not a verdict.

        For each result, read crossref.title + (crossref.abstract or
        subjects) and compare to manuscript_contexts. Decide. Call
        `acknowledge_finding(slug, doi, verdict='approved'|'rejected',
        note='...')` to record your call.
        """
        return _references.validate_references(state, slug)

    # ─── verification findings (persisted CrossRef verdicts) ─────────────────
    @mcp.tool()
    def list_verification_findings(
        slug: str,
        only_unacknowledged: bool = True,
        only_problems: bool = True,
    ) -> list[dict[str, Any]]:
        """List CrossRef verification findings the dashboard's Sync DOIs
        button wrote — or that the agent itself wrote via validate_references.

        Defaults to only unacknowledged + only problems (unresolved /
        title_mismatch / missing_doi / error). Set both to False for the
        full audit log.

        Call at session start to surface hallucinations the user already
        flagged in the dashboard.
        """
        return _verification.list_verification_findings(
            state, slug,
            only_unacknowledged=only_unacknowledged,
            only_problems=only_problems,
        )

    @mcp.tool()
    def acknowledge_finding(
        slug: str,
        doi: str,
        verdict: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Record the agent's judgment on one finding.

        `verdict`:
          - "approved" — cited paper fits the manuscript context.
            Sets context_verified=True so the dashboard's ribbon flips
            green. Use AFTER you've actually read the CrossRef title/
            abstract and the surrounding manuscript prose, not just
            because the DOI resolves.
          - "rejected" — citation is wrong (real DOI on the wrong paper).
            Sets context_verified=False. Pair with deleting the bad ref
            or replacing it via add_reference_by_doi.
          - None — no context decision; just dismiss from the active list.

        Always include a brief `note` explaining the reasoning. It lands
        on the finding doc as `acknowledged_note`.
        """
        return _verification.acknowledge_finding(
            state, slug, doi, verdict=verdict, actor="agent", note=note,
        )

    @mcp.tool()
    def clear_findings(slug: str) -> dict[str, Any]:
        """Wipe all verification findings for a paper. Use before a fresh
        full re-validation if you want the audit log reset.
        """
        return {"deleted": _verification.clear_findings(state, slug)}

    # ─── analyses ────────────────────────────────────────────────────────────
    @mcp.tool()
    def create_analysis(
        slug: str,
        name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        return _analyses.create_analysis(state, slug, name=name, description=description)

    @mcp.tool()
    def update_analysis(
        slug: str,
        name: str,
        description: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return _analyses.update_analysis(state, slug, name, description=description, status=status)

    @mcp.tool()
    def get_analysis(slug: str, name: str) -> dict[str, Any]:
        return _analyses.get_analysis(state, slug, name)

    @mcp.tool()
    def list_analyses(slug: str, status: str | None = None) -> list[dict[str, Any]]:
        return _analyses.list_analyses(state, slug, status=status)

    @mcp.tool()
    def delete_analysis(slug: str, name: str) -> dict[str, Any]:
        return {"deleted": _analyses.delete_analysis(state, slug, name)}

    # ─── compute-server registry ─────────────────────────────────────────────
    @mcp.tool()
    def add_server(
        alias: str,
        host: str,
        user: str,
        cores: int = 1,
        memory_gb: int | None = None,
        gpus: int = 0,
        ssh_key: str | None = None,
        conda_root: str | None = None,
        default_workdir: str | None = None,
        polite_max_cores_pct: int = 50,
        notes: str | None = None,
    ) -> dict[str, Any]:
        return _servers.add_server(
            state, alias=alias, host=host, user=user, cores=cores,
            memory_gb=memory_gb, gpus=gpus, ssh_key=ssh_key,
            conda_root=conda_root, default_workdir=default_workdir,
            polite_max_cores_pct=polite_max_cores_pct, notes=notes,
        )

    # ─── pipelines (account-wide, versioned) ─────────────────────────────────
    @mcp.tool()
    def register_pipeline(
        name: str,
        description: str | None = None,
        repo: str | None = None,
        notes: str | None = None,
        public_notes: str | None = None,
        executor: str | None = None,
        license: str | None = None,
    ) -> dict[str, Any]:
        """Create/update a workflow pipeline's identity. ACCOUNT-wide, like servers.

        TWO note fields, separate on purpose:
          `notes`        — PRIVATE, never published. Machine-specific facts go
                           here ("egress to EBI 43 B/s, don't download here").
          `public_notes` — published with the pipeline. What an adopter needs:
                           resource requirements, what it was tested against,
                           known limitations.
        One field with a "share this?" flag would put the private text a single
        wrong argument away from going public; two fields cannot be confused.

        `executor` says what runs it: nextflow | snakemake | script | wdl | cwl |
        make | other (default nextflow). The processes/edges/params model fits a
        plain bash or python pipeline just as well — recording edge formats and
        parameter defaults is what makes those re-runnable — so say which it is
        rather than putting "not a Nextflow pipeline" in the notes.

        This is the stable part only — name, repo, description. The process
        graph, the parameters and the edge formats belong to a VERSION, because
        "which version produced this figure" is a methods-section question."""
        return _pipelines.register_pipeline(state, name=name,
                                            description=description, repo=repo,
                                            notes=notes, public_notes=public_notes,
                                            executor=executor, license=license)

    @mcp.tool()
    def register_pipeline_version(
        name: str,
        version: str,
        processes: list[dict[str, Any]] | None = None,
        edges: list[dict[str, Any]] | None = None,
        params: list[dict[str, Any]] | None = None,
        engine_version: str | None = None,
        nextflow_version: str | None = None,
        description: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Register one version's process graph, edge formats and parameters.

            processes=[{"name":"fastp","label":"fastp","tool":"fastp",
                        "container":"biocontainers/fastp:0.23.4"}, …]
            edges=[{"from":"fastp","to":"star","format":"fastq.gz"}, …]
            params=[{"name":"--genome","default":"GRCh38","required":true,
                     "description":"iGenomes key"}, …]

        `format` on an edge is what actually moves between two steps — the thing
        you need when wiring a new dataset in.

        Versions are IMMUTABLE by default: `overwrite=True` only to fix a
        mis-registration, never to edit a released version, or every past
        "produced by v1.2" becomes wrong. An edge naming an undeclared process is
        rejected rather than silently dropped, and a cycle is rejected with the
        processes named."""
        return _pipelines.register_pipeline_version(
            state, name, version, processes=processes, edges=edges, params=params,
            engine_version=engine_version, nextflow_version=nextflow_version,
            description=description,
            overwrite=overwrite)

    @mcp.tool()
    def publish_pipeline(name: str, published: bool = True,
                         public_notes: str | None = None,
                         license: str | None = None) -> dict[str, Any]:
        """Share a pipeline with other Scivo accounts, or take it back private.

        Pipelines are PRIVATE by default and publishing is the only thing that
        changes that. It copies the identity, the process graphs and the
        parameters to a public registry — and deliberately NOT `notes`, which is
        where machine-specific facts live ("egress to EBI 43 B/s"). Fields added
        to the record in future stay private until they are added to the public
        projection on purpose.

        `public_notes` is the note written FOR adopters and IS published — set it
        here, or beforehand via register_pipeline. It never touches the private
        `notes`.

        Returns what was shared and what was withheld, so you can tell the user
        exactly what went out, plus a suggestion when a pipeline is published with
        nothing said to whoever picks it up."""
        return _pipelines.publish_pipeline(state, name, published=published,
                                           public_notes=public_notes,
                                           license=license)

    @mcp.tool()
    def search_public_pipelines(
        query: str | None = None,
        executor: str | None = None,
        include_own: bool = False,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """Search pipelines other accounts have published, to reuse instead of
        rebuilding.

        Every term of `query` must appear in the name, repo, description or in one
        of the process/tool names — so "rnaseq star" finds a Nextflow RNA-seq
        pipeline whose graph contains a STAR step. Returns summaries; call
        get_public_pipeline for the full graph, and import_public_pipeline to take
        a private copy you can run and adapt."""
        return _pipelines.search_public_pipelines(
            state, query, executor=executor, include_own=include_own, limit=limit)

    @mcp.tool()
    def get_public_pipeline(public_id: str) -> dict[str, Any]:
        """One published pipeline in full — every version's graph and params."""
        return _pipelines.get_public_pipeline(state, public_id)

    @mcp.tool()
    def import_public_pipeline(
        public_id: str, name: str | None = None, overwrite: bool = False,
    ) -> dict[str, Any]:
        """Copy a published pipeline into your account, private.

        A copy, not a reference: the original owner can unpublish or change theirs
        at any time, and a workflow you have already run against has to keep
        meaning what it meant. The copy starts unpublished — republishing someone
        else's work should be a decision, not a side effect of adopting it.

        The copy records `derived_from` — a structured link to the source — and
        that field IS published. So improving an imported pipeline and publishing
        it carries the attribution automatically; you do not have to remember to
        credit anyone. What you DO have to decide is the license (the reply says
        whether the original stated one) and whether the inherited `public_notes`
        still describes your version."""
        return _pipelines.import_public_pipeline(
            state, public_id, name=name, overwrite=overwrite)

    @mcp.tool()
    def list_pipelines() -> list[dict[str, Any]]:
        """Every pipeline registered on this account."""
        return _pipelines.list_pipelines(state)

    @mcp.tool()
    def list_pipeline_versions(name: str) -> list[dict[str, Any]]:
        """Every registered version of one pipeline, newest first."""
        return _pipelines.list_pipeline_versions(state, name)

    @mcp.tool()
    def get_pipeline(name: str, version: str | None = None) -> dict[str, Any]:
        """A pipeline with one version's full graph. Defaults to the latest."""
        return _pipelines.get_pipeline(state, name, version)

    @mcp.tool()
    def delete_pipeline_version(name: str, version: str) -> bool:
        """Remove one registered version."""
        return _pipelines.delete_pipeline_version(state, name, version)

    @mcp.tool()
    def delete_pipeline(name: str) -> bool:
        """Remove a pipeline and all its versions."""
        return _pipelines.delete_pipeline(state, name)

    # ─── datasets ────────────────────────────────────────────────────────────
    @mcp.tool()
    def register_dataset(
        name: str,
        path: str,
        kind: str = "other",
        server_alias: str | None = None,
        id_convention: str | None = None,
        joins_with: list[dict[str, Any]] | None = None,
        canonical: bool = True,
        superseded_by: str | None = None,
        n_records: int | None = None,
        notes: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Record WHERE a dataset lives and HOW it is keyed.

        `add_server` says which machines exist; this says which data is on them.
        `server_alias=None` means local. `kind`: expression_matrix | annotation |
        genome | metadata | reads | variants | alignment | phenotype | other.

        `id_convention` must carry a REAL example, not a description —
        "Glyma.01G000100 (Wm82.a4 gene ids)", not "soybean gene ids". Four
        conventions in one project, discovered by opening files one at a time, is
        what this field exists for; an id mismatch does not raise, it shows up as
        "the signal is weak".

        `joins_with` records what it connects to AND WHAT IT DOES NOT:
            [{"dataset": "sl-gff", "key": "gene_id", "joins": true},
             {"dataset": "sl-gff", "joins": false,
              "note": "quantified on a separate assembly — cannot be linked"}]
        The negative entry is the one that saves the half-day."""
        return _datasets.register_dataset(
            state, name=name, path=path, kind=kind, server_alias=server_alias,
            id_convention=id_convention, joins_with=joins_with,
            canonical=canonical, superseded_by=superseded_by,
            n_records=n_records, notes=notes, overwrite=overwrite)

    @mcp.tool()
    def list_datasets(
        kind: str | None = None,
        server_alias: str | None = None,
        canonical_only: bool = False,
    ) -> list[dict[str, Any]]:
        """Every dataset registered for this project.

        Call this BEFORE concluding what data exists. Searching the servers you
        happen to know about and concluding "there is no tissue information" is
        the reported failure — two finished analyses had to be re-run."""
        return _datasets.list_datasets(state, kind=kind, server_alias=server_alias,
                                       canonical_only=canonical_only)

    @mcp.tool()
    def get_dataset(name: str) -> dict[str, Any]:
        """One dataset record."""
        return _datasets.get_dataset(state, name)

    @mcp.tool()
    def update_dataset(
        name: str,
        path: str | None = None,
        kind: str | None = None,
        server_alias: str | None = None,
        id_convention: str | None = None,
        joins_with: list[dict[str, Any]] | None = None,
        canonical: bool | None = None,
        superseded_by: str | None = None,
        n_records: int | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Patch a dataset record; only the supplied fields change."""
        return _datasets.update_dataset(
            state, name, path=path, kind=kind, server_alias=server_alias,
            id_convention=id_convention, joins_with=joins_with,
            canonical=canonical, superseded_by=superseded_by,
            n_records=n_records, notes=notes)

    @mcp.tool()
    def check_dataset(name: str, count_lines: bool = False) -> dict[str, Any]:
        """Verify a dataset's path and report what CHANGED since the last check.

        Not just "does it exist" — a file that is still there but no longer the
        file you recorded is the failure that matters, so size/mtime are compared
        against the stored values. `count_lines` runs `wc -l` (off by default: it
        reads the whole file) and compares against the recorded `n_records`.
        An ssh failure returns `checked: false` + `error`, never `exists: false`."""
        return _datasets.check_dataset(state, name, count_lines=count_lines)

    @mcp.tool()
    def link_dataset(name: str, paper: str | None = None,
                     analysis: str | None = None) -> dict[str, Any]:
        """Attach a dataset to a paper (and optionally one of its analyses).

        `prepare_export` then returns the paper's datasets, so an "Availability
        of data and materials" statement is written from the record instead of
        reassembled by hand."""
        return _datasets.link_dataset(state, name, paper=paper, analysis=analysis)

    @mcp.tool()
    def delete_dataset(name: str) -> bool:
        """Remove a dataset record (the data itself is untouched)."""
        return _datasets.delete_dataset(state, name)

    @mcp.tool()
    def list_servers(active_only: bool = True) -> list[dict[str, Any]]:
        return _servers.list_servers(state, active_only=active_only)

    @mcp.tool()
    def get_server(alias: str) -> dict[str, Any]:
        return _servers.get_server(state, alias)

    @mcp.tool()
    def update_server(
        alias: str,
        host: str | None = None,
        user: str | None = None,
        cores: int | None = None,
        polite_max_cores_pct: int | None = None,
        default_workdir: str | None = None,
        active: bool | None = None,
    ) -> dict[str, Any]:
        return _servers.update_server(
            state, alias, host=host, user=user, cores=cores,
            polite_max_cores_pct=polite_max_cores_pct,
            default_workdir=default_workdir, active=active,
        )

    @mcp.tool()
    def delete_server(alias: str) -> dict[str, Any]:
        return {"deleted": _servers.delete_server(state, alias)}

    @mcp.tool()
    def add_server_env(
        alias: str,
        env_name: str,
        env_type: str = "conda",
        python_version: str | None = None,
        key_packages: list[str] | None = None,
    ) -> dict[str, Any]:
        return _servers.add_server_env(
            state, alias, env_name=env_name, env_type=env_type,
            python_version=python_version, key_packages=key_packages,
        )

    @mcp.tool()
    def list_server_envs(alias: str) -> list[dict[str, Any]]:
        return _servers.list_server_envs(state, alias)

    @mcp.tool()
    def delete_server_env(alias: str, env_name: str) -> dict[str, Any]:
        return {"deleted": _servers.delete_server_env(state, alias, env_name)}

    # ─── per-project server working directories ──────────────────────────────
    @mcp.tool()
    def set_project_workdir(server_alias: str, workdir: str,
                            description: str = "", env_name: str = "") -> dict[str, Any]:
        """Bind how THIS project uses a registered server: `workdir` (absolute
        path where this project's data/code/outputs live), `description` (what's
        in it), and `env_name` (the conda/venv env this project uses there).
        submit_remote_job uses the workdir as the base dir and activates the env
        by default (both falling back to the server's defaults), so each
        project's runs land in — and are documented against — a clear location
        and environment."""
        return _workdirs.set_project_workdir(state, server_alias, workdir,
                                             description=description, env_name=env_name)

    @mcp.tool()
    def list_project_workdirs() -> list[dict[str, Any]]:
        """List this project's server working-directory bindings (alias →
        workdir + description)."""
        return _workdirs.list_project_workdirs(state)

    @mcp.tool()
    def delete_project_workdir(server_alias: str) -> dict[str, Any]:
        """Remove this project's working-directory binding for a server."""
        return {"deleted": _workdirs.delete_project_workdir(state, server_alias)}

    # ─── analysis runs ───────────────────────────────────────────────────────
    @mcp.tool()
    def record_analysis_run(
        slug: str,
        analysis: str,
        command: str,
        host: str = "local",
        env_name: str | None = None,
        pid: int | None = None,
        log_path: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Insert a run record (provenance for a command you ran yourself).

        The row starts UNFINISHED. If the command has already finished, follow
        with `mark_run_finished(...)` — a row with no `pid` has no process for
        `poll_remote_pids` to check, so nothing else closes it until
        `auto_finish_stale_runs` sweeps it as a provenance row.
        """
        return _runs.record_analysis_run(
            state, slug, analysis, command=command, host=host,
            env_name=env_name, pid=pid, log_path=log_path, notes=notes,
        )

    @mcp.tool()
    def list_analysis_runs(
        slug: str,
        analysis: str,
        unfinished_only: bool = False,
        host: str | None = None,
    ) -> list[dict[str, Any]]:
        return _runs.list_analysis_runs(
            state, slug, analysis, unfinished_only=unfinished_only, host=host,
        )

    @mcp.tool()
    def get_analysis_run(slug: str, analysis: str, run_key: str) -> dict[str, Any]:
        return _runs.get_analysis_run(state, slug, analysis, run_key)

    @mcp.tool()
    def get_user_secret(key: str) -> dict[str, Any]:
        """Read an account-wide integration secret for the signed-in user (shared
        across all their projects; set in the dashboard Account tab or with
        set_user_secret). Returns {key, value} where value is null if unset — use
        it at call time (e.g. a Zenodo/API token)."""
        return {"key": key, "value": _secrets.get_user_secret(state, key)}

    @mcp.tool()
    def list_user_secrets() -> list[dict[str, Any]]:
        """List the user's stored account-wide secret keys (names + updated_at
        only, never the values)."""
        return _secrets.list_user_secrets(state)

    @mcp.tool()
    def set_user_secret(key: str, value: str) -> dict[str, Any]:
        """Store an account-wide secret for the signed-in user. Prefer the
        dashboard Account tab so the value isn't pasted into the chat transcript."""
        return _secrets.set_user_secret(state, key, value)

    @mcp.tool()
    def delete_user_secret(key: str) -> dict[str, Any]:
        """Delete an account-wide secret. Returns {deleted: bool}."""
        return {"deleted": _secrets.delete_user_secret(state, key)}

    @mcp.tool()
    def list_authors() -> list[dict[str, Any]]:
        """List the account-wide author library (name + affiliation + email +
        orcid), shared across all the user's projects. Reuse these on any
        paper's author list instead of re-typing an author + their affiliation.
        Also editable in the dashboard Account tab."""
        return _authors.list_authors(state)

    @mcp.tool()
    def add_author(name: str, affiliation: str = "", email: str = "",
                   orcid: str = "", affiliation_ids: list[str] | None = None) -> dict[str, Any]:
        """Add a reusable author to the account library. Idempotent on
        (name, affiliation) — repeated calls return the existing entry instead
        of duplicating it. `affiliation_ids` (optional) references the account
        affiliation library so a reused author carries their normalized
        multi-affiliation mapping. Returns the author doc (with its `id`)."""
        return _authors.add_author(state, name, affiliation=affiliation,
                                   email=email, orcid=orcid,
                                   affiliation_ids=affiliation_ids)

    @mcp.tool()
    def update_author(author_id: str, name: str = "", affiliation: str = "",
                      email: str = "", orcid: str = "",
                      affiliation_ids: list[str] | None = None) -> dict[str, Any]:
        """Update a library author's fields. Pass only the fields to change
        (empty string = leave unchanged). `affiliation_ids` (a list) replaces
        the author's references into the account affiliation library."""
        kw = {k: v for k, v in {"name": name, "affiliation": affiliation,
                                "email": email, "orcid": orcid}.items() if v}
        if affiliation_ids is not None:
            kw["affiliation_ids"] = affiliation_ids
        return _authors.update_author(state, author_id, **kw)

    @mcp.tool()
    def delete_author(author_id: str) -> dict[str, Any]:
        """Delete an author from the account library. Returns {deleted: bool}."""
        return {"deleted": _authors.delete_author(state, author_id)}

    @mcp.tool()
    def lint_manuscript(slug: str) -> dict[str, Any]:
        """Deterministic manuscript QA over a paper's sections. Returns grouped
        warnings + a summary; `summary.clean == True` means zero issues. Run
        before marking sections complete and resolve every warning (hard
        done-gate).

        Groups: DUPLICATION (same sentence restated across sections),
        SECTION_LEAKAGE (results/measurements in Methods, procedure in Results,
        a number in Methods+display item but never Results), STYLE (LLM tells,
        run-ons, bare comparatives, em-dashes, prose-form display refs,
        estimator voice, colloquial register, bare reviewer numbering), and
        INSIDER_CONTEXT (prose framed from inside the authoring session —
        ADVISORY, weigh highest on letters). Every rule, with the evidence
        behind it and per-rule guidance, is documented in /paper-writing
        ("Writing craft") — read that when a warning is unclear.

        Document-kind aware: a response/cover letter (own paper or section) is
        held to correspondence standards, and exemptions are returned in
        SUPPRESSED_BY_PROFILE rather than dropped — read it before treating a
        clean result as clean."""
        return _manuscript_lint.lint_manuscript(state, slug)

    @mcp.tool()
    def lint_legends(slug: str) -> dict[str, Any]:
        """Deterministic legend QA — the figure/table analogue of lint_manuscript.

        Returns one finding per flagged item; `level` is warn if any flag is
        warn-grade. Flags: **caption_only** (see below), long, body_duplication
        (every duplicated sentence enumerated in duplicated_spans),
        **number_restatement**, interpretive, sample_roster_restatement,
        bare_cross_reference, and table-only column_redundant /
        excluded_data_note in caption_smells. The rules and the
        caption/Methods/Results split are documented in /paper-writing
        ("Trimming a caption can delete the paper's method").

        **interpretive** flags a legend sentence making a claim instead of
        describing the panel — an evaluative intensifier (markedly,
        overwhelmingly), an inference (as expected, driven by, consistent with),
        or a comparison/outcome verb (larger, matches, exceeds). Each offending
        SENTENCE is in `interpretive_spans`. Comparisons are deliberately NOT
        flagged in a sentence about the graphic ("Darker shading indicates higher
        coverage", "The lower panel shows…") — describing the encoding is what a
        legend is for. One such sentence is info; 2+ is warn, because that is a
        legend that has grown a mini-Results.

        **number_restatement** fires when 3+ measurement-shaped numbers in the
        caption (percentages, thousands-separated counts, ×10^n magnitudes) are
        already shown in the item's OWN cells or in a section body — a caption
        walking through the values instead of pointing at them. Every offending
        number is listed in `duplicated_numbers` with its source, so they clear
        in one pass. Word count does not surface this: a numeric-dense caption
        can be short. One quoted headline value is deliberately NOT flagged.

        **caption_only is the one flag that means RELOCATE, not delete**, and it
        is ranked first. It fires when a parameter-shaped token (± 250 kb,
        q < 0.05, seed = 42, a software version) appears in the caption and in NO
        section body — i.e. the caption is its only carrier, so trimming it
        removes the value from the paper. Move it to Methods (threshold/constant)
        or Results (derived statistic) FIRST, then drop it from the caption. Every
        other flag here invites deletion; this is the only one whose absence can
        destroy information. It and number_restatement can never fire on the same
        token — a parameter is claimed by caption_only, a measurement by the
        restatement rule — so the report never tells you to both keep and cut the
        same value."""
        return _legend_lint.lint_legends(state, slug)

    @mcp.tool()
    def set_paper_authors(slug: str, authors: list[dict[str, Any]]) -> dict[str, Any]:
        """Set a paper's ordered author list. Each author is a dict with
        `name` (required) and optional `affiliation` (free-text fallback) /
        `affiliation_ids` (list of ids into the paper's affiliation list) /
        `email` / `orcid` / `corresponding` (bool → † + email listed; multiple
        allowed) / `equal_contribution` (bool → * + a shared "contributed
        equally" footnote). Pick entries from list_authors() to reuse the
        account library. Replaces the list."""
        return _papers.set_paper_authors(state, slug, authors)

    @mcp.tool()
    def list_affiliations() -> list[dict[str, Any]]:
        """List the account-wide affiliation library (reusable institution
        strings shared across papers/projects), also editable in the Account
        tab. Reference these by id from a paper's affiliation list."""
        return _affiliations.list_affiliations(state)

    @mcp.tool()
    def add_affiliation(text: str) -> dict[str, Any]:
        """Add a reusable affiliation to the account library. Idempotent on the
        text — repeated calls return the existing entry (with its `id`)."""
        return _affiliations.add_affiliation(state, text)

    @mcp.tool()
    def update_affiliation(affiliation_id: str, text: str) -> dict[str, Any]:
        """Change a library affiliation's text. Updates the LIBRARY entry only —
        papers keep the affiliation text captured when it was added (a
        point-in-time record; this does NOT rewrite existing papers). To pull a
        corrected text into an in-progress draft, call resync_paper_affiliations."""
        return _affiliations.update_affiliation(state, affiliation_id, text)

    @mcp.tool()
    def delete_affiliation(affiliation_id: str) -> dict[str, Any]:
        """Delete an affiliation from the account library. Returns {deleted}."""
        return {"deleted": _affiliations.delete_affiliation(state, affiliation_id)}

    @mcp.tool()
    def set_paper_affiliations(slug: str, affiliations: list[dict[str, Any]]) -> dict[str, Any]:
        """Set a paper's ordered, de-duplicated affiliation list — the numbered
        list authors reference by id (superscripts in the exported author
        block). Each entry is a dict with `text` (required) and optional `id`,
        or a plain string. Assign ids to authors via set_paper_authors(...,
        affiliation_ids=[...])."""
        return _papers.set_paper_affiliations(state, slug, affiliations)

    @mcp.tool()
    def set_paper_submission(slug: str, status: str, journal: str = "",
                             submitted_at: str = "", manuscript_id: str = "",
                             url: str = "", decision_at: str = "", notes: str = "") -> dict[str, Any]:
        """Track a paper's JOURNAL-SUBMISSION status (peer-review pipeline stage,
        shown on the paper card + Paper tab). `status` is one of: submitted,
        under_review, major_revision, minor_revision, accepted, in_press,
        published, rejected — or "" to clear (not submitted). Optional metadata:
        journal (where submitted), submitted_at (date), manuscript_id, url,
        decision_at, notes. Distinct from the writing status (draft/complete)."""
        return _papers.set_paper_submission(
            state, slug, status=status, journal=journal or None,
            submitted_at=submitted_at or None, manuscript_id=manuscript_id or None,
            url=url or None, decision_at=decision_at or None, notes=notes or None)

    @mcp.tool()
    def resync_paper_affiliations(slug: str) -> dict[str, Any]:
        """Opt-in: refresh a paper's cached affiliation text from the account
        library by id (for a DRAFT whose affiliation was renamed/corrected).
        Papers snapshot text at insert time and are never rewritten
        automatically; this is the explicit, user-triggered pull. Returns the
        paper with `resynced` = how many entries changed."""
        return _papers.resync_paper_affiliations(state, slug)

    @mcp.tool()
    def get_plan() -> dict[str, Any]:
        """Return the project owner's subscription plan + limits (authoritative,
        from the user's billing state): plan_id, tier (free/pro/max),
        subscription_status, is_trial, plan_expires_at, can_generate_images, and
        limits (image_quota_month, upload_limit_mb, project_cap, storage_gb).
        Use to know whether a paid-only feature (image generation, 500MB+
        uploads) is available before attempting it."""
        return _plan.get_plan(state)

    @mcp.tool()
    def heartbeat_run(slug: str, analysis: str, run_key: str) -> dict[str, Any]:
        """Mark a run as still alive so the dashboard keeps its live spinner
        instead of aging it to "stale" (a run with no heartbeat past the TTL is
        shown as stale, not running). Call periodically while a long job you're
        watching is still going; no-op once the run is finished."""
        _runs.bump_heartbeat(state, slug, analysis, run_key)
        return {"ok": True}

    @mcp.tool()
    def mark_run_finished(
        slug: str,
        analysis: str,
        run_key: str,
        exit_code: int,
        notes: str | None = None,
    ) -> dict[str, Any]:
        return _runs.mark_run_finished(
            state, slug, analysis, run_key, exit_code=exit_code, notes=notes,
        )

    @mcp.tool()
    def launch_local_job(
        slug: str,
        analysis: str,
        command: str,
        workdir: str,
        env_name: str | None = None,
        conda_root: str | None = None,
    ) -> dict[str, Any]:
        """Spawn a long-running local job (detached). Returns run row with pid + log_path."""
        return _runs.launch_local_job(
            state, slug, analysis, command=command, workdir=workdir,
            env_name=env_name, conda_root=conda_root,
        )

    @mcp.tool()
    def reap_local_run(slug: str, analysis: str, run_key: str) -> dict[str, Any]:
        """Check if a local run's PID is gone; if so, mark it finished."""
        return _runs.reap_local_run(state, slug, analysis, run_key)

    # ─── SSH-bound server operations ─────────────────────────────────────────
    @mcp.tool()
    def server_status(alias: str) -> dict[str, Any]:
        """Live SSH check: load avg, memory, our running PIDs, warnings."""
        return _ssh_ops.server_status(state, alias)

    @mcp.tool()
    def submit_remote_job(
        slug: str,
        analysis: str,
        command: str,
        server_alias: str,
        env_name: str | None = None,
        workers: int | None = None,
        local_dir: str | None = None,
        sync_files: bool = True,
        force: bool = False,
    ) -> dict[str, Any]:
        """Politeness-checked SSH job submission (rsync + nohup, pidfile-idempotent)."""
        return _ssh_ops.submit_remote_job(
            state, slug, analysis, command=command, server_alias=server_alias,
            env_name=env_name, workers=workers, local_dir=local_dir,
            sync_files=sync_files, force=force,
        )

    @mcp.tool()
    def tail_remote_log(
        slug: str,
        analysis: str,
        run_key: str,
        lines: int = 50,
    ) -> dict[str, Any]:
        """Last N lines of a run's log file (remote or local)."""
        return _ssh_ops.tail_remote_log(state, slug, analysis, run_key, lines=lines)

    @mcp.tool()
    def refresh_log_tail(
        slug: str,
        analysis: str,
        run_key: str,
        lines: int = 50,
    ) -> dict[str, Any]:
        """Like tail_remote_log, but persists the tail onto the run doc so the
        dashboard's Runs tab can render it via its Firestore listener."""
        return _ssh_ops.refresh_log_tail(state, slug, analysis, run_key, lines=lines)

    @mcp.tool()
    def kill_remote_job(slug: str, analysis: str, run_key: str) -> dict[str, Any]:
        """SIGKILL the recorded PID + mark run finished."""
        return _ssh_ops.kill_remote_job(state, slug, analysis, run_key)

    @mcp.tool()
    def poll_remote_pids(alias: str) -> dict[str, Any]:
        """One SSH round-trip: close phantom rows for `alias`.

        Only rows that recorded a PID are pollable. If the probe itself could
        not run (host off-network, forced command), the rows are LEFT OPEN and
        reported as `undetermined` + `error` — unknown is never "dead".
        """
        return _ssh_ops.poll_remote_pids(state, alias)

    @mcp.tool()
    def auto_finish_stale_runs(since_hours: float | None = None) -> dict[str, Any]:
        """Bulk cleanup across all hosts (local + remote): close every
        unfinished run that cannot still be live.

        Handles and counts three kinds of row separately, returning
        {checked, finished, provenance_closed, still_running, undetermined,
        skipped_older_than_window, errors}:
          - a local/remote PID that is gone → `finished`
          - a row with NO pid — provenance written by `record_analysis_run`
            after a foreground command — → `provenance_closed`. It has no
            process to check, so nothing else will ever close it.
          - a host that cannot be probed keeps its rows open (`still_running`,
            with the unknown subset in `undetermined`, plus `errors`).

        Leave `since_hours` UNSET (default) to sweep every unfinished row
        regardless of age — that is what cleaning up months-old rows needs. If
        set, it narrows the sweep to rows started within the last N hours and
        reports the older rows it skipped in `skipped_older_than_window`.
        """
        return _ssh_ops.auto_finish_stale_runs(state, since_hours=since_hours)

    @mcp.tool()
    def scan_untracked_jobs(alias: str, min_etime_seconds: int = 60) -> dict[str, Any]:
        """Find detached job-like processes on `alias` not in analysis_runs.

        Reads `ps`, so it sees only jobs still RUNNING. For provenance that is
        already lost — a finished foreground run — use scan_recent_outputs."""
        return _ssh_ops.scan_untracked_jobs(state, alias, min_etime_seconds=min_etime_seconds)

    @mcp.tool()
    def scan_recent_outputs(
        alias: str,
        workdir: str | None = None,
        since_hours: float = 168.0,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Output files recently written on `alias`, beside the runs we recorded.

        The counterpart to scan_untracked_jobs, which reads `ps` and so can only
        ever see a LIVE job — while almost every provenance gap is a job that
        already finished. Use this when a paper's figures/tables have no
        `source_analysis` and you need to reconstruct what produced them.

        Reports both sides and does NOT compute "orphans": a recorded run does
        not declare which files it wrote, so nothing can prove a file came from
        no recorded run. "7 checkpoints in the window, 0 recorded runs" is the
        answer — you draw the conclusion, then back-fill with create_analysis +
        record_analysis_run and link via update_figure/update_table."""
        return _ssh_ops.scan_recent_outputs(
            state, alias, workdir=workdir, since_hours=since_hours, limit=limit)

    # ─── export ──────────────────────────────────────────────────────────────
    @mcp.tool()
    def prepare_export(
        slug: str,
        fields: list[str] | None = None,
        stage_dir: str | None = None,
    ) -> dict[str, Any]:
        """Pre-export bundle: manuscript text, bibtex, figures, warnings.

        `fields` narrows the reply to those top-level keys (e.g.
        ["sections", "tables"]) — use it on a large document, where the full
        bundle exceeds the reply limit and spills to a file. An unknown key
        raises. `stage_dir` also writes every figure's image blob there and adds
        `local_path` to each figure, for assembling a document yourself.
        """
        return _exports.prepare_export(state, slug, fields=fields,
                                       stage_dir=stage_dir)

    @mcp.tool()
    def export_to_path(
        slug: str,
        output_path: str,
        fmt: str | None = None,
        csl_path: str | None = None,
        upload_to_storage: bool = True,
        scope: str = "main",
        page_size: str = "a4",
    ) -> dict[str, Any]:
        """Run pandoc to produce a document; upload result to Cloud Storage.

        Place a table or figure IN the body by putting `![](table:N)` /
        `![](figure:N)` alone on a line where it belongs; anything not placed
        that way is collected into a Tables/Figures section at the end.
        `page_size` is "a4" (default) or "letter", for .docx output.

        `scope`: "main" (default) = manuscript + MAIN figures/tables only;
        "supplementary" = a standalone Supplementary Material file with only
        the supplementary (≥101) figures/tables; "all" = everything in one
        file. To deliver a journal package, export scope="main" and then
        scope="supplementary" to a second path.
        If a call to this tool times out or is aborted, do NOT retry blind: the
        export may have finished and only the reply been lost. Check
        `list_exports(slug)` for an entry whose `updated_at` is after the call and
        whose `size_bytes` matches the local file at `output_path`; if it matches,
        the export succeeded (a blind retry costs another full run and can leave a
        duplicate artifact under a second filename).
        """
        return _exports.export_to_path(
            state, slug, output_path=output_path, fmt=fmt,
            csl_path=csl_path, upload_to_storage=upload_to_storage, scope=scope,
            page_size=page_size,
        )

    @mcp.tool()
    def attach_export(
        slug: str,
        local_path: str,
        filename: str | None = None,
        scope: str = "supplementary",
    ) -> dict[str, Any]:
        """Upload a data file (CSV/XLSX/TSV/ZIP/…) to a paper's Exports tab so
        it ships with the submission package next to the rendered docx/pdf.

        For generated submission OUTPUTS that aren't pandoc-rendered (e.g. a
        large numeric supplementary table better delivered as a CSV than a
        200-row Word table). For source/reference INPUTS use add_material.
        `scope`: main | supplementary | all (default supplementary)."""
        return _exports.attach_export(
            state, slug, local_path=local_path, filename=filename, scope=scope,
        )

    @mcp.tool()
    def list_exports(slug: str) -> list[dict[str, Any]]:
        """List previously-exported files for a paper."""
        return _exports.list_exports(state, slug)

    @mcp.tool()
    def delete_export(slug: str, filename: str) -> dict[str, Any]:
        """Remove an attached/exported file from a paper's Exports area (doc +
        blob) so a stale supplementary file doesn't ship in the package.
        Returns {deleted: bool}."""
        return {"deleted": _exports.delete_export(state, slug, filename)}

    @mcp.tool()
    def rename_export(slug: str, filename: str, new_filename: str) -> dict[str, Any]:
        """Rename an attached/exported file (moves its blob + doc), so renaming a
        supplementary data file doesn't leave the old one behind as a duplicate.
        Returns the updated export metadata."""
        return _exports.rename_export(state, slug, filename, new_filename)

    # ─── journal CSL registry ────────────────────────────────────────────────
    @mcp.tool()
    def register_journal_csl(
        journal: str,
        csl_filename: str,
        notes: str | None = None,
    ) -> dict[str, Any]:
        """Pin a journal name to a CSL style filename for this project.

        Export auto-resolves a journal to a CSL file (in-code map → kebab
        guess) and downloads it from the citation-style-language/styles
        repo. When the guess is wrong, find the correct filename at
        https://github.com/citation-style-language/styles and register it
        here (e.g. journal "J. Exp. Bot." → "journal-of-experimental-botany.csl").
        It then takes precedence for every future export of that journal.
        """
        return _csl.register_journal_csl(state, journal, csl_filename, notes)

    @mcp.tool()
    def list_journal_csls() -> list[dict[str, Any]]:
        """List this project's journal → CSL registry entries."""
        return _csl.list_journal_csls(state)

    @mcp.tool()
    def delete_journal_csl(journal: str) -> dict[str, Any]:
        """Remove a journal's registry entry (export falls back to the
        in-code map / kebab guess for it again)."""
        return {"deleted": _csl.delete_journal_csl(state, journal)}

    # ─── image generation ────────────────────────────────────────────────────
    @mcp.tool()
    def generate_image(
        prompt: str,
        slug: str | None = None,
        figure_number: int | None = None,
        asset_filename: str | None = None,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        caption: str | None = None,
        overwrite: bool = False,
        apply_style: bool = True,
        quality: str | None = None,
        input_image: str | None = None,
        mask: str | None = None,
    ) -> dict[str, Any]:
        """Generate an image via the configured ImageGenerator (local or cloud-fn).

        Default backend (hosted service) is OpenAI gpt-image-2. Requires a
        Pro+ subscription — the /generate_image Cloud Function refuses with
        403 for free-plan users.

        Supported aspect_ratio values: "1:1" (1024x1024), "16:9"/"3:2"/
        "landscape" (1536x1024), "9:16"/"2:3"/"portrait" (1024x1536).

        `quality` (gpt-image: "low"/"medium"/"high"/"auto") is forwarded to the
        provider when set; leave None for the provider default. Higher quality
        costs more. The chosen aspect_ratio and quality are stored on the figure
        so a dashboard re-render reuses the same shape.

        If `figure_number` is set, registers the result as a figure for the paper
        (requires `slug`). Pass `overwrite=True` to replace an existing figure at
        that number instead of erroring. Otherwise stores as an asset:
        `papers/{slug}/assets/` when `slug` is given, else a PROJECT asset at
        `projects/{pid}/assets/` — so a video/other project needs no dummy paper.
        Download an asset back to disk with `get_asset`.

        The project's image style (set in the dashboard under Memory → Image
        style) is prepended to the prompt automatically. Pass
        `apply_style=False` to generate without it for a one-off image.

        Pass `input_image` (a local path, asset_id, or asset filename) to EDIT
        that image instead of generating from scratch — keep a recurring
        character's face while changing outfit/pose, outpaint a bust to
        full-body, or remove an object. An optional `mask` (same forms; a PNG
        whose transparent region is what gets regenerated) confines the edit.
        Editing is OpenAI-only.
        """
        return _images.generate_image(
            state, slug, prompt=prompt, figure_number=figure_number,
            asset_filename=asset_filename, aspect_ratio=aspect_ratio,
            model=model, caption=caption, overwrite=overwrite,
            apply_style=apply_style, quality=quality,
            input_image=input_image, mask=mask,
        )

    @mcp.tool()
    def list_assets(slug: str | None = None) -> list[dict[str, Any]]:
        """List generated image assets. With `slug` → a paper's assets; without →
        the project-scoped assets (projects/{pid}/assets/)."""
        return _images.list_assets(state, slug) if slug else _assets.list_assets(state)

    @mcp.tool()
    def get_asset(asset_id_or_filename: str, dest_path: str,
                  slug: str | None = None) -> dict[str, Any]:
        """Download an asset's bytes to `dest_path` (so ken_burns/montage etc.
        can consume it). Project-scoped by default; pass `slug` for a paper's
        assets. Returns {dest_path, filename, size_bytes}."""
        return _assets.get_asset(state, asset_id_or_filename, dest_path, slug=slug)

    @mcp.tool()
    def add_asset(local_path: str, filename: str | None = None,
                  note: str | None = None) -> dict[str, Any]:
        """Register a local file as a PROJECT asset (uploads the bytes to
        projects/{pid}/assets/). Use for stills you fetched yourself (e.g. a
        curl'd photo) so they're tracked + downloadable via get_asset."""
        return _assets.add_asset(state, local_path, filename=filename, note=note)

    @mcp.tool()
    def delete_asset(asset_id_or_filename: str, slug: str | None = None) -> dict[str, Any]:
        """Delete an asset. With `slug` → a paper's asset; without → a project asset."""
        if slug:
            return {"deleted": _images.delete_asset(state, slug, asset_id_or_filename)}
        return {"deleted": _assets.delete_asset(state, asset_id_or_filename)}

    # ─── decks (presentations built from a paper) ────────────────────────────
    @mcp.tool()
    def create_deck(
        slug: str,
        title: str,
        audience: str | None = None,
        duration_min: int | None = None,
        theme: str | None = None,
        image_style: str | None = None,
        aspect_ratio: str = "16:9",
        deck_id: str | None = None,
    ) -> dict[str, Any]:
        """Create or retrieve a presentation deck attached to a paper.
        Idempotent: returns the existing deck unchanged if `deck_id` is
        provided and already exists. `aspect_ratio` ('16:9' | '16:10' |
        '4:3') sets the exported PPTX page size. `image_style` is a
        free-form style hint prepended to every ai-image region's
        prompt for visual consistency (e.g., "minimalist watercolor,
        soft natural light, Korean researcher aesthetic, no text").
        """
        return _decks.create_deck(
            state, slug, title=title, audience=audience,
            duration_min=duration_min, theme=theme,
            image_style=image_style,
            aspect_ratio=aspect_ratio, deck_id=deck_id,
        )

    @mcp.tool()
    def get_deck(slug: str, deck_id: str) -> dict[str, Any]:
        return _decks.get_deck(state, slug, deck_id)

    @mcp.tool()
    def list_decks(slug: str) -> list[dict[str, Any]]:
        return _decks.list_decks(state, slug)

    @mcp.tool()
    def update_deck(
        slug: str,
        deck_id: str,
        title: str | None = None,
        audience: str | None = None,
        duration_min: int | None = None,
        theme: str | None = None,
        image_style: str | None = None,
        aspect_ratio: str | None = None,
        concept: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Patch deck-level fields. `concept` is the unity header
        (palette / typography / motif) inherited by every slide's
        prompt — the PPTX export also harvests accent/bg/text colors
        from it to theme native text slides. `aspect_ratio` is
        '16:9' | '16:10' | '4:3'. `image_style` is a free-form style
        hint prepended to every ai-image region's prompt for visual
        consistency across the deck — set ONCE at outline time, then
        per-slide prompts only describe the scene."""
        return _decks.update_deck(
            state, slug, deck_id, title=title, audience=audience,
            duration_min=duration_min, theme=theme,
            image_style=image_style,
            aspect_ratio=aspect_ratio, concept=concept, status=status,
        )

    @mcp.tool()
    def delete_deck(slug: str, deck_id: str) -> dict[str, Any]:
        return {"deleted": _decks.delete_deck(state, slug, deck_id)}

    @mcp.tool()
    def add_slide(
        slug: str,
        deck_id: str,
        slide_number: int,
        role: str,
        title: str,
        body: str = "",
        prompt: str = "",
        notes: str = "",
        code: str = "",
        render_mode: str = "code-shape",
        figure_number: int | None = None,
    ) -> dict[str, Any]:
        """Add a slide to a deck. `notes` is MANDATORY for any non-title
        slide — empty notes mean the presenter wings the take-home.
        Use `renumber_deck` after bulk add/delete to pack numbers.
        """
        return _decks.add_slide(
            state, slug, deck_id,
            slide_number=slide_number, role=role, title=title,
            body=body, prompt=prompt, notes=notes, code=code,
            render_mode=render_mode, figure_number=figure_number,
        )

    @mcp.tool()
    def update_slide(
        slug: str,
        deck_id: str,
        slide_id: str,
        slide_number: int | None = None,
        role: str | None = None,
        title: str | None = None,
        body: str | None = None,
        prompt: str | None = None,
        notes: str | None = None,
        code: str | None = None,
        render_mode: str | None = None,
        figure_number: int | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return _decks.update_slide(
            state, slug, deck_id, slide_id,
            slide_number=slide_number, role=role, title=title,
            body=body, prompt=prompt, notes=notes, code=code,
            render_mode=render_mode, figure_number=figure_number,
            status=status,
        )

    @mcp.tool()
    def delete_slide(slug: str, deck_id: str, slide_id: str) -> dict[str, Any]:
        return {"deleted": _decks.delete_slide(state, slug, deck_id, slide_id)}

    @mcp.tool()
    def list_slides(
        slug: str, deck_id: str, fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List a deck's slides in display order.

        Pass `fields` (e.g. ["title", "role", "render_mode"]) to project
        each slide to just those keys — `id` and `slide_number` are always
        included. Use it to skip the bulky `code`/`notes` text when you
        only need an index; the full payload can exceed the tool's token
        budget on a large deck."""
        return _decks.list_slides(state, slug, deck_id, fields=fields)

    @mcp.tool()
    def renumber_deck(slug: str, deck_id: str) -> dict[str, Any]:
        """Pack slide_numbers tightly starting at 1, preserving order.
        Call after bulk add/delete. Returns {count, old_to_new}."""
        return _decks.renumber_deck(state, slug, deck_id)

    @mcp.tool()
    def reorder_deck(slug: str, deck_id: str, order: list[str]) -> dict[str, Any]:
        """Set the slide order explicitly. `order` is the full list of slide ids
        (from list_slides) in the desired sequence; each is reassigned
        slide_number 1..N in one pass. `order` must be a permutation of the
        deck's current slide ids. The deck analogue of reorder_section. To move
        or reorder slides, prefer this over add_slide + renumber_deck. Returns
        {count, order}."""
        return _decks.reorder_deck(state, slug, deck_id, order)

    # ─── videos + YouTube — registered ONLY on machines that do video work ────
    # (env CO_SCIENTIST_ENABLE_VIDEO overrides; else the YouTube token file on
    # this machine is the signal). Every registered tool costs every session
    # context whether used or not, and this family is admin-only in practice.
    if _features.video_enabled():
        _register_video_tools(mcp, state)

    @mcp.tool()
    def list_deck_comments(
        slug: str, deck_id: str, status: str | None = "open",
    ) -> list[dict[str, Any]]:
        """Comments reviewers left on the deck's slides from the dashboard,
        each tagged with slide_number / slide_id / slide_title (and an
        optional region_id). `status='open'` (default) is the agent's
        to-do list — revise those slides, then `resolve_deck_comment`.
        The deck analogue of the manuscript review loop.
        """
        return _decks.list_deck_comments(state, slug, deck_id, status=status)

    @mcp.tool()
    def resolve_deck_comment(
        slug: str, deck_id: str, slide_id: str, comment_id: str,
        status: str = "resolved",
    ) -> dict[str, Any]:
        """Close a slide comment once addressed: status 'resolved'
        (done) or 'rejected' (declined), or 'open' to reopen.
        """
        return _decks.resolve_deck_comment(
            state, slug, deck_id, slide_id, comment_id, status=status,
        )

    @mcp.tool()
    def set_slide_regions(
        slug: str,
        deck_id: str,
        slide_id: str,
        regions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Lay out SEVERAL images on one slide — forces the slide to
        render_mode='hybrid'. Each region is a dict:
          {render_mode: "ai-image" | "code-shape" | "paper-figure",
           x, y, w, h: floats 0..1 — fractions of the slide,
           fit: "contain" (default — letterbox, never crop; figures /
                charts) | "cover" (fill the box, crop overflow;
                eyecatch / decorative),
           figure_number | prompt | code: type-specific source,
           caption: optional text under the image}
        Regions are assigned ids r1..rN in order; render each with
        render_region — which also records the rendered image's pixel
        size (image_width / image_height) on the region. Re-calling
        replaces the layout but keeps the rendered image of any region
        whose source is unchanged.
        """
        return _decks.set_slide_regions(
            state, slug, deck_id, slide_id, regions=regions,
        )

    # ─── deck rendering + PPTX export (Phase 3) ──────────────────────────────
    @mcp.tool()
    def render_slide(
        slug: str,
        deck_id: str,
        slide_id: str,
        local_path: str | None = None,
    ) -> dict[str, Any]:
        """Materialize one slide's image into Storage at
        papers/{slug}/decks/{deck_id}/slides/{N}.png.

        Modes handled by the MCP:
          - paper-figure : copies the existing figure blob
          - ai-image     : substitutes {accent}/{display_font} etc.
                           from deck.concept, calls generate_image
          - hybrid       : renders every region it can; returns a
                           per-region summary (code-shape regions land
                           in skipped[] — do those via render_region)

        Mode that needs agent help (run the code yourself, then pass the
        resulting PNG path here):
          - code-shape : pass `local_path="path/to/slide.png"`

        `text` slides carry no image — nothing to render.
        """
        return _deck_render.render_slide(
            state, slug, deck_id, slide_id, local_path=local_path,
        )

    @mcp.tool()
    def preview_slide(
        slug: str,
        deck_id: str,
        slide_id: str,
        output_path: str | None = None,
    ) -> dict[str, Any]:
        """FAST single-slide preview for the iteration loop — render just this
        `code` slide to a PNG (one LibreOffice pass) instead of re-exporting
        the whole deck. Edit → preview_slide → Read the returned
        `preview_png_local_path` → fix → repeat; run export_deck_to_pptx ONCE
        at the end. Returns this slide's code_errors / overlap_warnings /
        bounds_warnings / font_warnings / placeholder_warnings too. (Image-only
        slides should use render_slide — already fast.)"""
        return _deck_render.preview_slide(
            state, slug, deck_id, slide_id, output_path=output_path,
        )

    @mcp.tool()
    def render_region(
        slug: str,
        deck_id: str,
        slide_id: str,
        region_id: str,
        local_path: str | None = None,
    ) -> dict[str, Any]:
        """Render ONE region of a hybrid (multi-image) slide into Storage.

        paper-figure / ai-image regions: the MCP renders them — an
        ai-image region's aspect ratio is matched to its box, not the
        whole slide. code-shape regions: pass `local_path` to a PNG you
        produced locally.
        """
        return _deck_render.render_region(
            state, slug, deck_id, slide_id, region_id, local_path=local_path,
        )

    @mcp.tool()
    def render_deck(slug: str, deck_id: str) -> dict[str, Any]:
        """Render every slide we can do automatically. Skips code-shape /
        hybrid (returns them in `skipped[]` for agent follow-up). When
        every slide has an image_blob_path, flips deck.status to 'rendered'.
        """
        return _deck_render.render_deck(state, slug, deck_id)

    @mcp.tool()
    def export_deck_to_pptx(
        slug: str,
        deck_id: str,
        output_path: str,
        skip_pdf: bool = False,
        skip_png: bool = False,
        only_slides: list[int] | None = None,
    ) -> dict[str, Any]:
        """Emit a .pptx from a deck — and a sibling .pdf when LibreOffice
        is installed (the portable fallback; Keynote sometimes rejects
        python-pptx output).

        Image slides embed the rendered PNG, aspect-fitted. `text` slides
        (and any slide still missing a render) become NATIVE editable
        text — title + bullets — themed from the deck concept's palette.
        Page size follows the deck's `aspect_ratio`. Both files upload to
        papers/{slug}/decks/{deck_id}/exports/. python-pptx ships in the
        base install.

        Speed flags (a full export re-renders every slide): `skip_pdf` skips
        the LibreOffice PDF pass (the dominant cost) and thus the PNGs —
        PPTX only; `skip_png` keeps the PDF but skips per-slide PNGs;
        `only_slides=[N,…]` renders PNGs for just those slides. For tight
        single-slide iteration use `preview_slide` instead.
        """
        return _deck_render.export_deck_to_pptx(
            state, slug, deck_id, output_path=output_path,
            skip_pdf=skip_pdf, skip_png=skip_png, only_slides=only_slides,
        )

    # ─── feedback (bug / feature reports → developer triage) ─────────────────
    @mcp.tool()
    def report_feedback(
        type: str,
        title: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        """File a bug / error / feature report about **co-scientist / Scivo**
        — this harness, its tools, its skills, or the dashboard.

        **This is the only channel that reaches the people who maintain it.**
        When the user says "report this to the developer", "개발자한테 보내줘"
        or similar, they mean THIS tool. Do not use the host agent's own
        bug-reporting command: that goes to whoever makes Claude Code or Pi,
        who cannot see this project, this tool surface, or this dashboard —
        and the report is then gone from the user's side with nothing to show
        for it. It has happened.

        Lands in the dashboard's Feedback tab for this project, where the user
        can see it, and in the maintainer's cross-project triage view.

        `type` is one of bug | error | feature | other. Use it when you hit a
        tool bug or limitation, or the user describes a problem worth
        reporting."""
        return _feedback.report_feedback(state, type=type, title=title, body=body)

    @mcp.tool()
    def list_feedback(status: str | None = None) -> list[dict[str, Any]]:
        """List this project's feedback items (newest first); optional status
        filter (open | in_progress | addressed | declined). Check before
        filing a duplicate."""
        return _feedback.list_feedback(state, status=status)

    @mcp.tool()
    def update_feedback(
        feedback_id: str, title: str | None = None,
        body: str | None = None, type: str | None = None,
        reopen: bool = True,
    ) -> dict[str, Any]:
        """Edit an agent-filed feedback item — fix a mistake, or REMOVE
        sensitive info you included by accident (a secret, a private host/SSH
        address). Only source='agent' items; priority/dev_note untouched.
        NOTE: by default, editing an addressed/declined item RE-OPENS it
        (status→open) so the update re-enters triage. Pass reopen=False to append
        info (e.g. 'verified fixed') WITHOUT changing its status."""
        return _feedback.update_feedback(
            state, feedback_id, title=title, body=body, type=type, reopen=reopen,
        )

    @mcp.tool()
    def delete_feedback(feedback_id: str) -> dict[str, Any]:
        """Retract (delete) an agent-filed feedback item — e.g. it contained a
        mistake or sensitive info. Only source='agent' items. Returns {deleted}."""
        return {"deleted": _feedback.delete_feedback(state, feedback_id)}

    return mcp


def _register_video_tools(mcp: FastMCP, state: State) -> None:
    """The video/YouTube tool family. See features.video_enabled for why this
    is conditional — registration cost is paid by every session, and this
    family only matters on machines that actually produce video."""
    # ─── videos (project-level deliverables + timecode comments) ──────────────
    @mcp.tool()
    def add_video(
        title: str, video_id: str | None = None, local_path: str | None = None,
        aspect_ratio: str = "16:9", fps: float | None = None,
        duration_s: float | None = None, description: str | None = None,
        srt_local_path: str | None = None, ass_local_path: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Register a project video deliverable. Upload the mp4 via `local_path`
        (+ optional .srt/.ass sidecars); `aspect_ratio` is "16:9" or "9:16".
        Shown in the dashboard's Video tab (admin). Returns the video doc."""
        return _videos.add_video(
            state, title=title, video_id=video_id, local_path=local_path,
            aspect_ratio=aspect_ratio, fps=fps, duration_s=duration_s,
            description=description, srt_local_path=srt_local_path,
            ass_local_path=ass_local_path, overwrite=overwrite,
        )

    @mcp.tool()
    def list_videos() -> list[dict[str, Any]]:
        """List the project's video deliverables (newest first)."""
        return _videos.list_videos(state)

    @mcp.tool()
    def delete_video(video_id: str) -> dict[str, Any]:
        """Delete a video (and its comments). Returns {deleted}."""
        return {"deleted": _videos.delete_video(state, video_id)}

    @mcp.tool()
    def list_video_comments(
        video_id: str | None = None, status: str | None = "open",
    ) -> list[dict[str, Any]]:
        """Timecode comments (open by default), sorted by (video, t_seconds).
        `video_id=None` spans all videos — the agent's re-cut/re-caption to-do
        list. Each carries `t_seconds` (and `frame` when known)."""
        return _videos.list_video_comments(state, video_id, status=status)

    @mcp.tool()
    def resolve_video_comment(
        video_id: str, comment_id: str, status: str = "resolved",
        response: str | None = None,
    ) -> dict[str, Any]:
        """Mark a timecode comment resolved/rejected (or open to reopen) after
        acting on it; optionally record what changed in `response`."""
        return _videos.resolve_video_comment(
            state, video_id, comment_id, status=status, response=response,
        )

    @mcp.tool()
    def count_open_video_comments() -> int:
        """Count open, human-authored timecode comments across the project."""
        return _videos.count_open_video_comments(state)

    # ─── YouTube publishing (MCP-local upload; opt-in per-user OAuth) ──────────
    @mcp.tool()
    def youtube_connect(
        client_id: str | None = None, client_secret: str | None = None,
    ) -> dict[str, Any]:
        """STEP 1 — start YouTube OAuth (device flow). Returns {verification_url,
        user_code} immediately (non-blocking): tell the user to open the URL and
        enter the code, then call youtube_complete_connect(). Needs a YouTube
        Data API OAuth client via YOUTUBE_CLIENT_ID/SECRET env or the args."""
        return _youtube.youtube_connect(state, client_id=client_id, client_secret=client_secret)

    @mcp.tool()
    def youtube_complete_connect() -> dict[str, Any]:
        """STEP 2 — finish the connection after the user authorized in the
        browser. Polls briefly, stores the refresh token, returns {connected}.
        If not authorized yet, returns {pending: true} — call again."""
        return _youtube.youtube_complete_connect(state)

    @mcp.tool()
    def youtube_disconnect() -> dict[str, Any]:
        """Forget this machine's stored YouTube credentials."""
        return _youtube.youtube_disconnect(state)

    @mcp.tool()
    def youtube_upload(
        video_id: str, title: str | None = None, description: str = "",
        tags: list[str] | None = None, category_id: str = "22",
        privacy: str = "unlisted", made_for_kids: bool = False,
        publish_at: str | None = None, language: str | None = "ko",
        local_path: str | None = None, force: bool = False,
        playlist: str | None = None, thumbnail: str | None = None,
    ) -> dict[str, Any]:
        """Upload a Video-tab item to YouTube (or update metadata if already
        uploaded). Defaults to privacy='unlisted' — set 'public' ONLY after the
        user explicitly confirms; publishing is outward-facing. 9:16 ≤3min gets
        a #Shorts tag. Saves the YouTube id/URL on the Video doc (idempotent).
        `playlist` (id or exact title) files the video into that playlist after
        upload, creating it if the title is new — for series organization.
        `thumbnail` (local PNG/JPEG ≤2MB, e.g. 1280x720 or 1080x1920) sets a
        custom thumbnail in the same call; it needs a VERIFIED channel, and a
        refusal is reported in `thumbnail_error` instead of failing the upload.
        On a 9:16 SHORT it only replaces the 16:9 renditions (search/suggested
        cards) — the Shorts feed's vertical thumbnail is NOT settable by the API,
        and the result says so in `thumbnail.shorts_note`."""
        return _youtube.youtube_upload(
            state, video_id, title=title, description=description, tags=tags,
            category_id=category_id, privacy=privacy, made_for_kids=made_for_kids,
            publish_at=publish_at, language=language, local_path=local_path,
            force=force, playlist=playlist, thumbnail=thumbnail,
        )

    @mcp.tool()
    def youtube_set_thumbnail(video_id: str, thumbnail_path: str) -> dict[str, Any]:
        """Set a custom thumbnail on an already-uploaded video (thumbnails.set).
        `video_id` = a Video-tab slug (resolved to its uploaded YouTube id) or a
        raw YouTube id; `thumbnail_path` = local PNG/JPEG ≤2MB. Requires a
        verified channel (403 otherwise). Uses the existing YouTube connection.
        For a 9:16 SHORT this only changes the 16:9 renditions; the Shorts feed
        keeps a frame YouTube picked (not settable via any API) — the result
        carries `shorts_note`, so don't plan work around lifting Shorts-feed
        views with thumbnails."""
        return _youtube.youtube_set_thumbnail(state, video_id, thumbnail_path)

    @mcp.tool()
    def youtube_list_playlists() -> list[dict[str, Any]]:
        """List the connected channel's YouTube playlists — [{playlist_id, title,
        privacy, item_count, url}]. Uses the existing connection (no re-consent)."""
        return _youtube.youtube_list_playlists(state)

    @mcp.tool()
    def youtube_create_playlist(title: str, description: str = "",
                                privacy: str = "public") -> dict[str, Any]:
        """Create a YouTube playlist. Returns {playlist_id, title, privacy, url}.
        `privacy` is public|unlisted|private."""
        return _youtube.youtube_create_playlist(
            state, title, description=description, privacy=privacy)

    @mcp.tool()
    def youtube_add_to_playlist(playlist_id_or_title: str, video_id: str) -> dict[str, Any]:
        """Add a video to a playlist. `playlist_id_or_title` = a playlist id or an
        exact title; `video_id` = a Video-tab slug (resolved to its uploaded
        YouTube id) or a raw YouTube id."""
        return _youtube.youtube_add_to_playlist(state, playlist_id_or_title, video_id)

    @mcp.tool()
    def youtube_status(video_id: str) -> dict[str, Any]:
        """Return a Video item's stored YouTube publish state (id/URL/privacy)
        and whether this machine is connected."""
        return _youtube.youtube_status(state, video_id)

    @mcp.tool()
    def youtube_check() -> dict[str, Any]:
        """Pre-flight the YouTube connection (no video_id): refresh the token and
        call channels.list?mine=true. Catches a revoked token (invalid_grant) or
        a channel-less account BEFORE a render/upload. Returns {connected,
        has_channel, channel_title, channel_id, uploads_ok} or a clear error.
        Run this before /video-publish."""
        return _youtube.youtube_check(state)

