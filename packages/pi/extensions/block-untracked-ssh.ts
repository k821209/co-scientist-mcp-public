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

// ── what a line RUNS through ssh ─────────────────────────────────────────────
// This used to ask two questions of the whole text: is there a line that STARTS
// with `ssh`, and is there a `nohup` / `disown` / trailing `&` anywhere.
// Replayed over the scenario corpus the scivo-harness guard is measured with
// (tests/data/guard_scenarios.json, 2026-11-19) it stopped nothing it should
// not have — and let 16 of 29 launches through: `cd x && ssh gpu "nohup …"`, a
// launch in a loop or an `if`, behind `timeout` or an environment assignment,
// through `bash -c`, `gcloud compute ssh`, `sshpass`, a detached tmux or
// screen, `setsid`.
//
// So the line is read the way the shell reads it. This is the reader of the
// Python hook (packages/hooks/pretool_block_ssh_nohup.py) and of the harness's
// guardrails.py, written a third time because an extension is one file. The
// three are held together by the corpus, and this one is also replayed
// against the Python hook over the same lines (tests/test_pi_guard_scenarios.py).
const REMOTE_PROGRAMS = new Set(["ssh", "autossh", "mosh"]);
// Programs whose arguments are text to show or to look for, never to run.
const TEXT_PROGRAMS = new Set([
  "echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "man", "which", "type", "whatis",
  "apropos", "apt", "apt-get", "dnf", "yum", "brew", "pip", "pip3",
]);
const SHELLS = new Set(["bash", "sh", "zsh", "dash", "ksh"]);
const KEYWORDS = new Set(["do", "then", "else", "elif", "if", "while", "until", "time", "!", "{", "}"]);
const ASSIGNMENT = /^[A-Za-z_][A-Za-z0-9_]*=/;
const DETACHES =
  /\bnohup\b|\bsetsid\b|\bdisown\b|\bscreen\s+-d\w*|\btmux\s+new(?:-session)?\b[^\n]*?\s-d\b|(?<![&|<>])&(?![&|>])/i;
const NESTING_LIMIT = 4;
const TOKEN_RE = /[A-Za-z0-9_.@-]+/g;
// Rule 2 only: is there an ssh or a copy on the line at all.
const SSH_CMD_RE = /^\s*ssh\b/m;
const HEREDOC = /<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1(.*?)^[ \t]*\2[ \t]*$/gms;
const SEPARATOR = /(?:\n|;|\|\||&&|\|)/;

/** The line cannot be cut into commands with any confidence. */
export class Unreadable extends Error {}

interface Word { text: string; quoted: boolean; at: number }
interface Command { words: Word[]; stop: number; background: boolean; inner: string[]; payload: string }
export interface RemoteCall { remote: string; background: boolean }

/** The command with the heredoc bodies it merely WRITES removed. A body fed to
 *  ssh (`ssh host bash <<EOF … EOF`) is the remote command and stays. */
export function executableText(command: string): string {
  return command.replace(HEREDOC, (whole: string, _q: string, tag: string, _body: string, offset: number) => {
    const head = command.slice(0, offset);
    const parts = head ? head.split(SEPARATOR) : [""];
    const last = parts[parts.length - 1];
    return /\bssh\b/.test(last) ? whole : "<<" + tag + "\n" + tag;
  });
}

function basename(text: string): string {
  const cut = text.lastIndexOf("/");
  return (cut < 0 ? text : text.slice(cut + 1)).toLowerCase();
}

/** The line as the shell would cut it: one entry per simple command. */
function commands(line: string): Command[] {
  const out: Command[] = [];
  const n = line.length;
  let i = 0;
  let words: Word[] = [];
  let inner: string[] = [];
  let pending: string[] = [];          // heredoc tags opened on this line
  let word: string[] | null = null;
  let quoted = false;
  let wordAt = 0;

  const endWord = () => {
    if (word !== null) words.push({ text: word.join(""), quoted, at: wordAt });
    word = null; quoted = false;
  };
  const endCommand = (stop: number, background = false) => {
    endWord();
    if (words.length) out.push({ words, stop, background, inner, payload: "" });
    words = []; inner = [];
  };
  const open = (at: number) => { if (word === null) { word = []; wordAt = at; } return word; };
  const substitution = (at: number): number => {
    let depth = 1;
    let j = at;
    while (j < n) {
      if (line[j] === "\\") { j += 2; continue; }
      if (line[j] === "(") depth += 1;
      else if (line[j] === ")") { depth -= 1; if (depth === 0) return j + 1; }
      j += 1;
    }
    throw new Unreadable("a $( that never closes");
  };

  while (i < n) {
    const ch = line[i];
    if (ch === "\\" && i + 1 < n) {
      const w = open(i);
      if (line[i + 1] !== "\n") w.push(line[i + 1]);
      i += 2;
      continue;
    }
    if (ch === "'") {
      const close = line.indexOf("'", i + 1);
      if (close < 0) throw new Unreadable("a ' that never closes");
      open(i).push(line.slice(i + 1, close));
      quoted = true;
      i = close + 1;
      continue;
    }
    if (ch === '"') {
      const w = open(i);
      quoted = true;
      let j = i + 1;
      for (;;) {
        if (j >= n) throw new Unreadable('a " that never closes');
        if (line[j] === "\\" && j + 1 < n) { w.push(line[j + 1]); j += 2; }
        else if (line[j] === '"') break;
        else if (line.startsWith("$(", j)) {
          const close = substitution(j + 2);
          inner.push(line.slice(j + 2, close - 1));
          w.push(line.slice(j, close));
          j = close;
        } else if (line[j] === "`") {
          const close = line.indexOf("`", j + 1);
          if (close < 0) throw new Unreadable("a ` that never closes");
          inner.push(line.slice(j + 1, close));
          w.push(line.slice(j, close + 1));
          j = close + 1;
        } else { w.push(line[j]); j += 1; }
      }
      i = j + 1;
      continue;
    }
    if (ch === "#" && word === null) {
      const stop = line.indexOf("\n", i);
      i = stop < 0 ? n : stop;
      continue;
    }
    if (line.startsWith("$(", i)) {
      const close = substitution(i + 2);
      inner.push(line.slice(i + 2, close - 1));
      open(i).push(line.slice(i, close));
      quoted = true;                     // a substituted word is not a literal one
      i = close;
      continue;
    }
    if (ch === "`") {
      const close = line.indexOf("`", i + 1);
      if (close < 0) throw new Unreadable("a ` that never closes");
      inner.push(line.slice(i + 1, close));
      open(i).push(line.slice(i, close + 1));
      quoted = true;
      i = close + 1;
      continue;
    }
    if (line.startsWith("<<", i) && !line.startsWith("<<<", i)) {
      const match = /^<<-?\s*(['"]?)([A-Za-z_][A-Za-z0-9_]*)\1/.exec(line.slice(i));
      if (match) {
        endWord();
        pending.push(match[2]);
        i += match[0].length;
        continue;
      }
    }
    if (ch === "\n") {
      if (pending.length) {
        // The lines up to each tag are the heredoc's, not commands.
        endWord();
        const bodyFrom = i + 1;
        let at = bodyFrom;
        for (const tag of pending) {
          const closing = new RegExp("^[ \\t]*" + tag + "[ \\t]*$", "gm");
          closing.lastIndex = at;
          const found = closing.exec(line);
          if (!found) throw new Unreadable("a heredoc that never closes");
          at = found.index + found[0].length;
        }
        if (words.length) out.push({ words, stop: i, background: false, inner, payload: line.slice(bodyFrom, at) });
        words = []; inner = []; pending = [];
        i = at;
        continue;
      }
      endCommand(i);
      i += 1;
      continue;
    }
    if (ch === " " || ch === "\t") { endWord(); i += 1; continue; }
    if (ch === ";") { endCommand(i); i += 1; continue; }
    if (ch === "|") { endCommand(i); i += 1; continue; }
    if (ch === "&") {
      const before = i ? line[i - 1] : "";
      const after = i + 1 < n ? line[i + 1] : "";
      if (after === "&") { endCommand(i); i += 2; continue; }
      if (before === "<" || before === ">" || after === ">") { open(i).push(ch); i += 1; continue; }
      endCommand(i, true);
      i += 1;
      continue;
    }
    if (ch === "(" || ch === ")") { endCommand(i); i += 1; continue; }
    open(i).push(ch);
    i += 1;
  }
  if (pending.length) throw new Unreadable("a heredoc that never closes");
  endCommand(n);
  return out;
}

/** What this line hands to a remote machine, one entry per `ssh` it runs.
 *  Throws `Unreadable` when it cannot tell. */
export function remoteCalls(line: string, depth = 0): RemoteCall[] {
  if (depth > NESTING_LIMIT) throw new Unreadable("nested too deep to follow");
  const found: RemoteCall[] = [];
  for (const command of commands(line)) {
    for (const text of command.inner) found.push(...remoteCalls(text, depth + 1));
    const words = [...command.words];
    // `do ssh …`, `VAR=value ssh …`: the command proper starts after these.
    while (words.length && ((KEYWORDS.has(words[0].text) && !words[0].quoted) || ASSIGNMENT.test(words[0].text))) {
      words.shift();
    }
    if (!words.length) continue;
    const program = basename(words[0].text);
    if (SHELLS.has(program) || program === "eval") {
      // One shell deeper: its `-c` string (or eval's arguments) is a line to read.
      const rest = words.slice(1).map((w) => w.text);
      const scripts = program === "eval"
        ? rest
        : rest.slice(0, -1).flatMap((text, k) => (/^-[a-z]*c$/.test(text) ? [rest[k + 1]] : []));
      for (const script of scripts) found.push(...remoteCalls(script, depth + 1));
    }
    if (TEXT_PROGRAMS.has(program)) continue;
    for (let position = 0; position < words.length; position++) {
      const { text, quoted, at } = words[position];
      if (!REMOTE_PROGRAMS.has(basename(text))) continue;
      // As an argument, a quoted "ssh" is a string someone is passing along.
      // As the program, quoted or not, it is what runs.
      if (quoted && position) continue;
      // `nohup ssh …`, `setsid ssh …`: left running from this side.
      const ahead = words.filter((w) => w.at < at && !w.quoted).map((w) => w.text).join(" ");
      found.push({
        remote: line.slice(at, command.stop) + "\n" + command.payload,
        background: command.background || /\b(nohup|setsid)\b/i.test(ahead),
      });
      break;
    }
  }
  return found;
}

/** The registered server a launch on this line reaches, or null to allow.
 *
 *  Fail-open on an empty alias set: letting a possibly-untracked job through is
 *  a smaller harm than breaking every Bash call on a machine whose cache has not
 *  been written yet. A launch on a machine that is not in the registry is not
 *  this guard's to stop: it has no Runs tab row to be missing from. */
export function blockedTarget(command: string, aliases: Set<string>): string | null {
  if (aliases.size === 0) return null;
  if (hasOverride(command)) return null;
  const text = executableText(command);
  const everywhere = text.match(TOKEN_RE) ?? [];
  let calls: RemoteCall[];
  try {
    calls = remoteCalls(text);
  } catch {
    // A line that cannot be read, or a reader that fails: never a pass — the
    // whole line, by the words alone.
    if (/\bssh\b/i.test(text) && DETACHES.test(text)) {
      return everywhere.find((token) => aliases.has(token)) ?? null;
    }
    return null;
  }
  for (const call of calls) {
    if (!(call.background || DETACHES.test(call.remote))) continue;
    let tokens = call.remote.match(TOKEN_RE) ?? [];
    // `ssh $h …` in a loop names its machines somewhere else on the line.
    if (call.remote.includes("$")) tokens = [...tokens, ...everywhere];
    const hit = tokens.find((token) => aliases.has(token));
    if (hit) return hit;
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
    `Ask mcp__scivo__remote_workdir("${hit.alias}") for the path and use it; to bind a different`,
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
    "  mcp__scivo__submit_remote_job(",
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
