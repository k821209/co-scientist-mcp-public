"""FastMCP server: registers tool functions for Claude Code over stdio."""
from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .guide import GUIDE_VERSION, render_guide
from .state import State
from .tools import activity as _activity
from .tools import analyses as _analyses
from .tools import csl as _csl
from .tools import decks as _decks
from .tools import deck_render as _deck_render
from .tools import exports as _exports
from .tools import feedback as _feedback
from .tools import imports as _imports
from .tools import figures as _figures
from .tools import images as _images
from .tools import materials as _materials
from .tools import memory as _memory
from .tools import papers as _papers
from .tools import references as _references
from .tools import reorder as _reorder
from .tools import requirements as _requirements
from .tools import reviews as _reviews
from .tools import runs as _runs
from .tools import sections as _sections
from .tools import servers as _servers
from .tools import ssh_ops as _ssh_ops
from .tools import tables as _tables
from .tools import todos as _todos
from .tools import verification as _verification


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
            from .version_check import check_version
            info.update(check_version())
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
        return render_guide()

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
    def list_papers() -> list[dict[str, Any]]:
        """List all papers for the active user."""
        return _papers.list_papers(state)

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
    ) -> list[dict[str, Any]]:
        """List reviews for a paper, optionally filtered by status, source, and/
        or the user's triage `decision` ('pending'|'accepted'|'rejected'). The
        author triages comments in the dashboard; `decision='accepted'` is the
        set they've approved you to act on (no decision == 'pending')."""
        return _reviews.list_reviews(
            state, slug, status=status, source=source, decision=decision)

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
    def count_open_user_comments(slug: str) -> int:
        """How many unresolved human comments exist — dashboard ('user') AND
        shared/public-page ('external') feedback, excluding AI reviewer notes.
        Used for the SessionStart banner."""
        return _reviews.count_open_user_comments(state, slug)

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
    ) -> dict[str, Any]:
        """Register a figure. If local_path provided, uploads image bytes to Storage."""
        return _figures.add_figure(
            state, slug, figure_number=figure_number, title=title,
            caption=caption, legend=legend, local_path=local_path,
        )

    @mcp.tool()
    def update_figure(
        slug: str,
        figure_number: int,
        title: str | None = None,
        caption: str | None = None,
        legend: str | None = None,
        local_path: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Patch a figure; optionally replace the image bytes."""
        return _figures.update_figure(
            state, slug, figure_number, title=title, caption=caption,
            legend=legend, local_path=local_path, status=status,
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
    def list_figures(slug: str, supplementary: bool = False) -> list[dict[str, Any]]:
        return _figures.list_figures(state, slug, supplementary=supplementary)

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

    # ─── tables ──────────────────────────────────────────────────────────────
    @mcp.tool()
    def add_table(
        slug: str,
        table_number: int,
        title: str,
        content: str,
        caption: str | None = None,
    ) -> dict[str, Any]:
        return _tables.add_table(
            state, slug, table_number=table_number, title=title,
            content=content, caption=caption,
        )

    @mcp.tool()
    def update_table(
        slug: str,
        table_number: int,
        title: str | None = None,
        content: str | None = None,
        caption: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        return _tables.update_table(
            state, slug, table_number, title=title, content=content,
            caption=caption, status=status,
        )

    @mcp.tool()
    def get_table(slug: str, table_number: int) -> dict[str, Any]:
        return _tables.get_table(state, slug, table_number)

    @mcp.tool()
    def list_tables(slug: str, supplementary: bool = False) -> list[dict[str, Any]]:
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
    ) -> dict[str, Any]:
        return _references.add_reference(
            state, slug, citation_key=citation_key, title=title, authors=authors,
            journal=journal, year=year, doi=doi, pmid=pmid, bibtex=bibtex,
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
    ) -> dict[str, Any]:
        return _references.update_reference(
            state, slug, citation_key, title=title, authors=authors,
            journal=journal, year=year, doi=doi, pmid=pmid, bibtex=bibtex,
        )

    @mcp.tool()
    def get_reference(slug: str, citation_key: str) -> dict[str, Any]:
        return _references.get_reference(state, slug, citation_key)

    @mcp.tool()
    def list_references(slug: str) -> list[dict[str, Any]]:
        return _references.list_references(state, slug)

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
        title/authors/journal/year from CrossRef. Won't overwrite existing
        non-empty fields.
        """
        return _references.enrich_reference_from_doi(state, slug, citation_key)

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
        """One SSH round-trip: close phantom rows for `alias`."""
        return _ssh_ops.poll_remote_pids(state, alias)

    @mcp.tool()
    def auto_finish_stale_runs() -> dict[str, Any]:
        """Bulk cleanup across all hosts (local + remote)."""
        return _ssh_ops.auto_finish_stale_runs(state)

    @mcp.tool()
    def scan_untracked_jobs(alias: str, min_etime_seconds: int = 60) -> dict[str, Any]:
        """Find detached job-like processes on `alias` not in analysis_runs."""
        return _ssh_ops.scan_untracked_jobs(state, alias, min_etime_seconds=min_etime_seconds)

    # ─── export ──────────────────────────────────────────────────────────────
    @mcp.tool()
    def prepare_export(slug: str) -> dict[str, Any]:
        """Pre-export bundle: manuscript text, bibtex, figures, warnings."""
        return _exports.prepare_export(state, slug)

    @mcp.tool()
    def export_to_path(
        slug: str,
        output_path: str,
        fmt: str | None = None,
        csl_path: str | None = None,
        upload_to_storage: bool = True,
        scope: str = "main",
    ) -> dict[str, Any]:
        """Run pandoc to produce a document; upload result to Cloud Storage.

        `scope`: "main" (default) = manuscript + MAIN figures/tables only;
        "supplementary" = a standalone Supplementary Material file with only
        the supplementary (≥101) figures/tables; "all" = everything in one
        file. To deliver a journal package, export scope="main" and then
        scope="supplementary" to a second path."""
        return _exports.export_to_path(
            state, slug, output_path=output_path, fmt=fmt,
            csl_path=csl_path, upload_to_storage=upload_to_storage, scope=scope,
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
        slug: str,
        prompt: str,
        figure_number: int | None = None,
        asset_filename: str | None = None,
        aspect_ratio: str = "1:1",
        model: str = "gpt-image-2",
        caption: str | None = None,
        overwrite: bool = False,
        apply_style: bool = True,
        quality: str | None = None,
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

        If `figure_number` is set, registers the result as a figure for the paper.
        Pass `overwrite=True` to replace an existing figure at that number
        instead of erroring. Otherwise stores as an asset under
        papers/{slug}/assets/.

        The project's image style (set in the dashboard under Memory → Image
        style) is prepended to the prompt automatically. Pass
        `apply_style=False` to generate without it for a one-off image.
        """
        return _images.generate_image(
            state, slug, prompt=prompt, figure_number=figure_number,
            asset_filename=asset_filename, aspect_ratio=aspect_ratio,
            model=model, caption=caption, overwrite=overwrite,
            apply_style=apply_style, quality=quality,
        )

    @mcp.tool()
    def list_assets(slug: str) -> list[dict[str, Any]]:
        """List generated image assets (non-figure) for a paper."""
        return _images.list_assets(state, slug)

    @mcp.tool()
    def delete_asset(slug: str, asset_id_or_filename: str) -> dict[str, Any]:
        return {"deleted": _images.delete_asset(state, slug, asset_id_or_filename)}

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
        """
        return _deck_render.export_deck_to_pptx(
            state, slug, deck_id, output_path=output_path,
        )

    # ─── feedback (bug / feature reports → developer triage) ─────────────────
    @mcp.tool()
    def report_feedback(
        type: str,
        title: str,
        body: str | None = None,
    ) -> dict[str, Any]:
        """File a bug / error / feature report for this project so the
        developer can triage it. `type` is one of bug | error | feature |
        other. Use when you hit a tool bug or limitation, or the user describes
        a problem worth reporting. Appears in the dashboard's Feedback tab."""
        return _feedback.report_feedback(state, type=type, title=title, body=body)

    @mcp.tool()
    def list_feedback(status: str | None = None) -> list[dict[str, Any]]:
        """List this project's feedback items (newest first); optional status
        filter (open | in_progress | addressed | declined). Check before
        filing a duplicate."""
        return _feedback.list_feedback(state, status=status)

    return mcp
