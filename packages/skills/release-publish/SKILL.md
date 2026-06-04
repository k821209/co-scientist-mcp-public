---
name: release-publish
description: Audit an analysis release folder and publish it as a standalone GitHub repository. Use when the user says "publish the code," "release the analysis," "make a GitHub repo for this," "prepare the code for submission."
---

# /release-publish

**Triggers:** "publish the analysis code," "release this to GitHub,"
"make the repo for reviewers," "code availability repo."

## What it does

Takes an analysis group's `release/` folder and publishes it as a
standalone public GitHub repo, with audit gates so half-baked or
secret-leaking code never gets pushed.

This is a git + filesystem workflow — it does NOT touch Firestore.
The MCP isn't involved beyond reading the analysis group's location.

## Flow

### 1. Resolve the release folder

The release folder is `analysis/<group>/release/`. If it doesn't
exist, ask the user whether to create it (copy the publishable subset
of `analysis/<group>/` into `release/`). Confirm the target before
proceeding.

### 2. Audit (ALWAYS — non-skippable)

Before any git operation, audit `release/` for:

- **Hardcoded values** — absolute paths (`/Users/`, `/home/`), API
  keys, secrets, machine-pinned hashes. (Reuse `/analysis-audit`
  Pass 1 logic.)
- **README accuracy** — does the README describe what's actually in
  the folder? Are the run instructions correct?
- **Remote reachability** — any URLs / DOIs in the README resolve?
- **Licensing** — is there a LICENSE file? If not, ask the user
  which license.

Three outcomes:
- **PASS** — proceed.
- **WARN** — show the report, get EXPLICIT user approval per warning
  before continuing.
- **FAIL** — refuse to push. Only continue if the user explicitly
  passes `--force` AND re-confirms each blocking issue individually.

### 3. Git state pre-flight

- Detect: is `release/` already a git repo, or new?
- If there's a nested-`.git` confusion (a `.git` somewhere up the
  tree that would swallow the release folder), **ABORT immediately**
  and explain. Don't try to untangle it automatically.

### 4. Stage explicitly

Build a manifest of the conventional release files:
- README, LICENSE
- scripts (`.py`, `.sh`, `.R`, `.nf`, …)
- small result artifacts (plots, summary CSVs)

Flag anything out of shape and require per-item approval:
- Large binaries (`.bam`, `.fastq.gz`, `.vcf.gz`) — usually shouldn't
  be in a code repo
- Harness artifacts, `__pycache__`, `.DS_Store`, editor files

**NEVER `git add .`** — stage the manifest explicitly so nothing
unexpected ships.

### 5. Commit

- New repo: `"Initial release of <repo-name>"`
- Existing repo update: ask the user for the commit message body.

Don't skip hooks. Don't `--no-verify`.

### 6. Push

- Add the remote if needed; verify origin consistency (the remote
  URL matches what the user expects).
- Push to `main`.
- **NEVER `--force` to main.** Under any circumstances. If the push
  is rejected for non-fast-forward, stop and surface it to the user.

### 7. Record the release

Append an entry to `analysis/<group>/RELEASE.md`:

```
## 2026-05-20
- repo:   https://github.com/<user>/<repo>
- commit: <SHA>
- note:   <what this release contains>
```

### 8. Post-push reminders

- Verify the GitHub repo's visibility (public for code-availability).
- If the manuscript has placeholder URLs ("code available at
  github.com/TODO"), suggest updating them via `/paper-writing` with
  the real repo URL.

## Hard rules

- **Never `git add .`** — explicit manifest only.
- **Never skip a FAIL audit** without `--force` + per-issue
  re-confirmation.
- **Never force-push to main.**
- **Abort on nested-repo confusion** — don't guess.
- **No credential prompts** — require pre-configured SSH / auth. If
  git asks for a password, stop and tell the user to set up SSH keys.
