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
 *  `pi install git:…` clones the repo and runs no `npm install`, so there is no
 *  `node_modules` beside this file. Importing the host's types
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

/** Every spelling of a registered server that could appear as an ssh target. */
export function loadAliases(readFile: (p: string) => string = (p) =>
  fs.readFileSync(p, "utf8")): Set<string> {
  const out = new Set<string>();
  try {
    const data = JSON.parse(readFile(cachePath())) as {
      servers?: { alias?: string; host?: string; user?: string }[];
    };
    for (const s of data.servers ?? []) {
      if (s.alias) out.add(s.alias);
      if (s.host) out.add(s.host);
      if (s.user && s.host) out.add(`${s.user}@${s.host}`);
    }
  } catch {
    // Missing/unreadable cache → empty set → fail open. See isBlocked.
  }
  return out;
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

    const target = blockedTarget(command, loadAliases());
    if (target) return { block: true, reason: reasonFor(target) };
  });
}
