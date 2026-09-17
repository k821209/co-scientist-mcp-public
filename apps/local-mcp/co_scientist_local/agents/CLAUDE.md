# Shipped subagents — the contract every reader here follows

Each file is a Claude Code subagent definition, linked into a project's
`.claude/agents/` on MCP startup (`agents_install.py`). They are READERS: a
skill hands one a bundle and it reports what the text required from outside
that bundle, or what the venue would not print. Two exist — `reviewer-frame-check`
(spawned by `/reviewer-frame-check` and `/cold-read`) and `journal-copyedit`
(spawned by `/prose-review`).

What a reader definition must have, and why:

- **`tools: Read`, nothing else.** Isolation is a capability boundary, not a
  request. A reader that CAN list or grep will, and is then no longer cold.
- **"Do not invoke directly with hand-written context"** in the description. The
  caller is, by construction, the agent that knows every contaminating fact.
- **Every finding carries a verbatim `span`** the caller can anchor a review row
  to, and — where the finding is a sentence — the replacement sentence. A
  finding the reader cannot rewrite is one it did not understand.
- **The closing blocks, in this order:** `--- PASSED ---` (so the caller can see
  the pass ran rather than stalled), `--- PATTERN ---` (a defect repeated nine
  times is one editing decision, not nine rows), `--- BUNDLE_NOTE ---` (what was
  wrong with the handoff — a fragment, a missing venue, a bundle too wide — since
  a pass on the wrong material produces findings that look valid). A reader
  that suppresses anything by profile lists it under `--- SUPPRESSED_BY_PROFILE ---`.
- **The one rule against noise:** vocabulary native to the field or ordinary
  academic brevity is not a finding. When unsure, flag with `uncertain: yes`
  rather than suppress.

Hosts without a fresh-context subagent (Codex, Pi) run the same definition in a
separate session with only the bundle open; the skill says so. Never make a
skill depend on one host's spawning mechanism by name.
