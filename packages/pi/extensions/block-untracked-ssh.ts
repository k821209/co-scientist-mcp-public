/**
 * Pi port of the Claude Code hook `pretool_block_ssh_nohup.py`.
 *
 * Why this is the one piece of glue the Pi package genuinely needs: the skills
 * and the MCP server both cross over unchanged (skills are already spec-compliant
 * Agent Skills, and pi-mcp-adapter reads the same .mcp.json), but Claude Code
 * hooks do not — Pi has its own event system. Without this, a raw
 * `ssh <alias> … nohup …` runs a job that never lands in `analysis_runs`, so it
 * is invisible in the dashboard's Running Jobs and its provenance is lost. That
 * is exactly the gap the provenance rules in project_guide() exist to close.
 *
 * Behaviour is kept identical to the Python hook on purpose — same aliases
 * source, same override words, same fail-open — so the two harnesses cannot
 * drift into blocking different things.
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Only the surface this extension touches, declared LOCALLY on purpose.
 *
 *  This ships as a cloned checkout that Pi loads by path, and Pi runs `npm
 *  install` only for npm and git sources — so there is no `node_modules` beside
 *  this file. Importing the host's types
 *  (`@earendil-works/pi-coding-agent`, as Pi's own example does) is erased by a
 *  transpiling loader but would fail a type-CHECKING one, and which of those Pi
 *  uses is not something this package should have to bet on. Structural typing
 *  makes the real ExtensionAPI assignable to this anyway. */
interface ToolCallEvent {
  toolName?: unknown;
  input?: unknown;
}
interface BlockResult {
  block: true;
  reason: string;
}
interface ExtensionAPI {
  on(
    event: "tool_call",
    handler: (event: ToolCallEvent) => Promise<BlockResult | void>,
  ): void;
}

/** Written by the local MCP at startup and after add_server/update_server. The
 *  hook reads a FILE rather than calling the registry, deliberately: a network
 *  round-trip on every Bash call would be felt. */
function cachePath(): string {
  return (
    process.env.CO_SCIENTIST_SERVERS_CACHE ??
    path.join(os.homedir(), ".co-scientist", "cache", "servers.json")
  );
}

type Cache = {
  servers?: { alias?: string; host?: string; user?: string }[];
  projects?: Record<string, Record<string, string>>;
};

function readCache(readFile: (p: string) => string): Cache {
  try {
    return JSON.parse(readFile(cachePath())) as Cache;
  } catch {
    return {}; // Missing/unreadable cache → fail open. See blockedTarget.
  }
}

/** Every spelling of a registered server that could appear as an ssh target. */
export function loadAliases(readFile: (p: string) => string = (p) =>
  fs.readFileSync(p, "utf8")): Set<string> {
  const out = new Set<string>();
  for (const s of readCache(readFile).servers ?? []) {
    if (s.alias) out.add(s.alias);
    if (s.host) out.add(s.host);
    if (s.user && s.host) out.add(`${s.user}@${s.host}`);
  }
  return out;
}

/** This project's root per server alias, from the cache's `projects` map. */
export function loadProjectRoots(
  projectId: string | null,
  readFile: (p: string) => string = (p) => fs.readFileSync(p, "utf8"),
): Record<string, string> {
  if (!projectId) return {};
  return readCache(readFile).projects?.[projectId] ?? {};
}

const PROJECT_ID_RE = /[Pp]roject\s+id\s*:\s*`([a-zA-Z0-9_-]+)`/;
const CONTEXT_FILES = ["CLAUDE.md", "AGENTS.md"];

/** The project id in the CLAUDE.md / AGENTS.md found walking up from cwd —
 *  the same file the MCP checks at startup. */
export function detectProjectId(
  cwd: string,
  readFile: (p: string) => string = (p) => fs.readFileSync(p, "utf8"),
): string | null {
  let dir = path.resolve(cwd);
  for (;;) {
    for (const name of CONTEXT_FILES) {
      try {
        const m = PROJECT_ID_RE.exec(readFile(path.join(dir, name)));
        if (m) return m[1];
      } catch {
        /* not here */
      }
    }
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

const OVERRIDE_PREFIXES = ["# setup", "# manual"];
const OVERRIDE_INLINE = "# allow-untracked";

export function hasOverride(command: string): boolean {
  const head = command.replace(/^\s+/, "");
  return (
    OVERRIDE_PREFIXES.some((p) => head.startsWith(p)) ||
    command.includes(OVERRIDE_INLINE)
  );
}

// Backgrounding markers. The trailing-& form requires preceding whitespace so
// that a redirect like `2>&1` does not read as backgrounding.
const BG_RE = /\bnohup\b|\bdisown\b|\s&\s*["']?\s*$/m;
// NOT positional. An option that takes a separate value (`-i key`, `-p 2222`,
// `-o k=v`) defeats any "skip the flags" pattern, and the Python hook this is
// ported from silently allowed those through until a parity test caught it. So:
// confirm it is an ssh invocation, then look for a registered alias among all
// tokens.
const SSH_CMD_RE = /^\s*ssh\b/m;
const TOKEN_RE = /[A-Za-z0-9_.@-]+/g;

/** The ssh target to block, or null to allow.
 *
 *  Fail-open on an empty alias set: letting a possibly-untracked job through is
 *  a smaller harm than breaking every Bash call on a machine whose cache has not
 *  been written yet. */
export function blockedTarget(command: string, aliases: Set<string>): string | null {
  if (aliases.size === 0) return null;
  if (hasOverride(command)) return null;
  if (!BG_RE.test(command)) return null;
  if (!SSH_CMD_RE.test(command)) return null;
  for (const m of command.matchAll(TOKEN_RE)) {
    if (aliases.has(m[0])) return m[0];
  }
  return null;
}

// Rule 2 — a directory outside this project's root on a registered server.
// `# setup` does NOT lift it (setup is exactly when a folder is made); only
// `# outside-project` does. Mirrors the Python hook, segment for segment.
const OUTSIDE_OVERRIDE = "# outside-project";
const SEG_SPLIT_RE = /\s*(?:;|&&|\|\||\|)\s*/;
const MKDIR_RE = /\bmkdir\b(.*)$/;
const COPY_RE = /\b(?:rsync|scp)\b(.*)$/;
const ABS_PATH_RE = /(?<![\w.@/])(\/[^\s"';|&]+)/g;
const REMOTE_DEST_RE = /^([A-Za-z0-9_.@-]+):(\/[^\s"';|&]*)$/;

export function outsideProject(
  command: string,
  aliases: Set<string>,
  roots: Record<string, string>,
): { alias: string; path: string; root: string } | null {
  if (command.includes(OUTSIDE_OVERRIDE)) return null;
  if (!SSH_CMD_RE.test(command) && !COPY_RE.test(command)) return null;
  let alias: string | null = null;
  for (const m of command.matchAll(TOKEN_RE)) {
    if (aliases.has(m[0])) { alias = m[0]; break; }
  }
  if (!alias) return null;
  const root = (roots[alias] ?? "").replace(/\/+$/, "");
  if (!root.startsWith("/")) return null;
  const outside = (p0: string) => {
    const p = p0.replace(/\/+$/, "") || "/";
    return !(p === root || p.startsWith(root + "/"));
  };
  const flat = command.replace(/["']/g, " ");
  for (const seg of flat.split(SEG_SPLIT_RE)) {
    const c = COPY_RE.exec(seg);
    if (c) {
      // rsync/scp: the DESTINATION is the last argument, and only a remote one
      // on this alias is ours to judge. Pulling from a shared path is reading.
      const args = c[1].trim().split(/\s+/).filter(Boolean);
      const d = args.length ? REMOTE_DEST_RE.exec(args[args.length - 1]) : null;
      if (d && d[1] === alias && d[2] && outside(d[2])) return { alias, path: d[2], root };
      continue;
    }
    const m = MKDIR_RE.exec(seg);
    if (!m) continue;
    for (const pm of m[1].matchAll(ABS_PATH_RE)) {
      if (outside(pm[1])) return { alias, path: pm[1], root };
    }
  }
  return null;
}

export function outsideReason(hit: { alias: string; path: string; root: string }): string {
  return [
    `Blocked: \`${hit.path}\` on ${hit.alias} is outside this project's directory there, \`${hit.root}\`.`,
    "",
    `Every folder this project makes on a server lives under that root (runs in ${hit.root}/analysis/<name>).`,
    `Ask mcp__co_scientist__remote_workdir("${hit.alias}") for the path and use it; to bind a different`,
    "root for this project, set_project_workdir(...).",
    "",
    "If this really must live elsewhere (shared reference data, say), add `# outside-project`",
    "to the command and say why.",
  ].join("\n");
}

export function reasonFor(target: string): string {
  return [
    `Blocked: raw \`ssh ${target} … nohup …\` bypasses Running Jobs and loses provenance.`,
    "",
    "Use the MCP tool instead:",
    "",
    "  mcp__co_scientist__submit_remote_job(",
    "    slug=..., analysis=..., command=...,",
    `    server_alias="${target}", env_name=..., workers=...,`,
    "  )",
    "",
    "It records the run in analysis_runs and surfaces it in the dashboard.",
    "",
    "Override (setup work like mkdir / env create): prefix the command with",
    "`# setup` or include `# allow-untracked` anywhere in the command.",
  ].join("\n");
}

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event) => {
    // Pi's shell tool is not necessarily named "Bash"; match either spelling
    // rather than assuming, and read the command defensively.
    const name = String(event.toolName ?? "");
    if (!/^(bash|shell)$/i.test(name)) return;
    const command = String(
      (event.input as { command?: unknown } | undefined)?.command ?? "",
    ).trim();
    if (!command) return;

    const aliases = loadAliases();
    const roots = loadProjectRoots(detectProjectId(process.cwd()));
    const hit = outsideProject(command, aliases, roots);
    if (hit) return { block: true, reason: outsideReason(hit) };
    const target = blockedTarget(command, aliases);
    if (target) return { block: true, reason: reasonFor(target) };
  });
}
