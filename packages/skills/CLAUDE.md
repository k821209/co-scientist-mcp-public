# Editing a skill — read before changing any SKILL.md here

Skills are prose about code, and the copy that drifts is the one nobody is
looking at; it fails only when followed. A review of all 27 on 2026-09-02 found
a call that raises (`add_table(legend=)`, written from a docstring that was
itself wrong), an example missing a required argument, a lint list naming 8 of
17 kinds, and one skill contradicting its own hard rule twenty lines apart.
Every one was a skill restating something the code already states.

`tests/test_skill_audit.py` now gates publishing: unknown tool names, keyword
arguments the tool does not accept, `/refs` to skills that do not exist,
skills the guide never lists, and a stated skill count that is not the number
on disk all fail the suite, and `scripts/publish-public.sh` refuses to ship on
a failing suite. **It cannot catch the three things below.** Those are yours,
every time you open one of these files — for the file you are touching, not as
a sweep.

## 1. Point at the tool. Do not restate it.

Never enumerate a tool's parameters, return keys, lint kinds, or status values
in a skill. Name the tool, say WHY it is called and what to do with the
result, and let the docstring — which is version-locked with the code — carry
the rest. `summary.by_kind` beats a list of kinds that is wrong by the next
release.

## 2. A rule lives once, in `project_guide()`.

The submitted-baseline rule was copied into six skills; one contradicted
itself. When a skill needs a rule the guide already states, reference the
guide's section and write only what is different on this skill's surface. The
shape to copy is `/paper-revision`'s "read `/paper-writing` §2a; here are the
four failures specific to revising."

## 3. `paper-deck` is ~1,900 lines and cannot be reviewed.

The review sampled it. Do not add to it. The next edit that touches it should
split a core `SKILL.md` (rules) from reference documents (examples, catalogs,
recorded cases), the way its own `reference_corpus/` already works.

## Also

- Do not state how many skills exist. The audit checks the two places that do.
- Outward-facing actions — publish, upload, send, `register_submission` — happen
  only after the user says so. That rule belongs in the guide (see 2); a skill
  that turns it into an unconditional call is the highest-severity thing the
  review found.
- Say in the commit message what you cleaned in the file you touched, so a
  skipped pass is visible in the log.
