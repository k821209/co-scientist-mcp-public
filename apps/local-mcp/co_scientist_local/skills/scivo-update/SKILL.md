---
name: scivo-update
description: Update the Scivo MCP and its skills from inside a session, and say what restart it then needs. Use when whoami or the session banner says an update is available, or the user says "update scivo," "업데이트 해줘," "새 버전으로 올려줘," or types /update outside the scivo harness.
---

# /scivo-update

In the `scivo` harness this is `/update`, which updates and brings the session
back by itself — use that there, not this. Claude Code, Codex and Pi cannot
restart themselves, so here it is the two halves a session CAN do: run the
update, and tell the user exactly what is left for them.

Before this skill the only way was a line the user had to copy out of
`whoami`'s hint or the Setup tab and paste into a terminal, which reads as
"there is no way to update" (user, 2026-11-16).

## Flow

1. `mcp__scivo__whoami()`. Its description says what the version fields mean.
   - `install_warning` or `context_warning` present → say it first. An update
     on top of a replaced or mis-wired install may not do what the user expects.
   - `update_available` is `false` → say the install is current, with
     `installed_version` and `git_sha`, and stop. Do not run anything.
   - `true`, or `null` (an editable install cannot be compared) → go on.
2. **Run the update with the shell tool, in the project directory.** The
   command is the one `update_hint` names: the interpreter in
   `python_executable`, then `-m co_scientist_local update`. Take the
   interpreter from `whoami`, never a bare `python3` — a different one on PATH
   updates an environment nothing is wired to, and the session then reports
   "updated" while running the old code.
   Add `--check` first if the user asked only what an update would do.
3. Read what it printed and relay it: the version before, each step's ✓ or ✗,
   the version after. A step marked ✗ is reported with its message, not
   summarised as "updated with warnings".
4. **Say the restart, and stop working.** The server this session talks to
   imported its code when the session started and cannot swap it: until the
   session (or the MCP server, where the host can reconnect one) is restarted,
   every tool here is still the old build. Tell the user to restart, and that
   the first `whoami()` afterwards should show the new version with
   `stale_process: false`. Do not carry on with other work in this session as
   if it were updated — a lint that comes back clean now is the old lint.

## What it does not do

- It does not restart anything. Saying "updated" without the restart is the
  failure this skill is most likely to cause.
- It does not update the host itself (Claude Code, Codex, Pi) — that is the
  vendor's own command.
- For Pi, the skills come from the checkout Pi was pointed at: the update
  brings the MCP up to date, and `git pull` in that checkout brings the
  skills. Say both.
