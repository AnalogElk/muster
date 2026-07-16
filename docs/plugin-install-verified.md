# Verified install (do not paraphrase)

Verified **2026-07-15** against `github.com/AnalogElk/muster` @ `340d721`, from a
clean temp directory, on Claude Code 2.1.211. These exact strings are what the
homepage hero must use. Everything below was observed, not read in a doc.

## The install

```
/plugin marketplace add AnalogElk/muster
/plugin install muster@muster
```

It is **two commands, not one**. `/plugin install muster` alone is invalid: the
marketplace must be added first.

Observed output (via the CLI equivalents, see note):

```
$ claude plugin marketplace add AnalogElk/muster
Refreshing marketplace cache (timeout: 120s)…
Cloning repository (timeout: 120s): https://github.com/AnalogElk/muster.git
Clone complete, validating marketplace…
✔ Successfully added marketplace: muster (declared in user settings)

$ claude plugin install muster@muster
Installing plugin "muster@muster"...✔ Successfully installed plugin: muster@muster (scope: user)
2 userConfig options not yet set — run /plugin configure muster@muster in Claude Code, or pass --config KEY=VALUE.
```

> **Note on how this was verified.** `/plugin ...` is a slash command and is not
> available in headless (`claude -p`) mode: it returns "/plugin isn't available
> in this environment." The equivalent CLI subcommands (`claude plugin
> marketplace add`, `claude plugin install`) were used instead and both
> succeeded. The slash form is what a user types interactively.

## The loop proof, with no Docker and no configuration

From a clean directory, immediately after install, an agent read the real board:

```
$ claude -p "Use the items tool from the plugin:muster:muster-board MCP server to
   read 3 rows of the os_tasks collection. Print only each row's name and status."
   --allowedTools "mcp__plugin_muster_muster-board__items"

P1 — Compose core: Postgres + Directus up green locally — completed
P2 — Directus os_* schema snapshot + profile seed (generic Demo Co / AE) — completed
Elk OS — KB ingestion step (manifest load into the bundled RAG engine) — pending
```

Those are the actual rows that built Muster. No Docker, no signup, no config.

## Component inventory as installed

```
$ claude plugin details muster@muster
muster 0.1.3
  Skills (5)  board, connect, doctor, muster-protocol, up
  Agents (0)
  Hooks (1)  SessionStart  (harness-only — no model context cost)
  MCP servers (1)  muster-board  (tool schemas resolved at runtime; not counted)
  Projected token cost
  Always-on:   ~220 tok   added to every session
```

Note Claude Code reports `commands/*.md` under **Skills**, not a separate
Commands section.

## Facts the hero must not get wrong

1. **The install is two lines.** Do not compress it to one.
2. **`userConfig` defaults DO work for the MCP server.** Despite the "2 userConfig
   options not yet set" message at install, `${user_config.*}` resolves to the
   declared defaults. Confirmed:
   ```
   $ claude mcp get plugin:muster:muster-board
     Status: ✔ Connected
     URL: https://cms.musterr.dev/mcp
     Headers:
       Authorization: [REDACTED]
   ```
   So `/muster:connect` genuinely needs zero arguments against the demo board.
3. **The MCP server's real name is `plugin:muster:muster-board`**, not
   `muster-board`. Plugin MCP servers are namespaced `plugin:<plugin>:<server>`,
   and its tools are `mcp__plugin_muster_muster-board__*`.
4. **First use of an MCP tool needs a one-time permission grant.** In an
   interactive session the user approves a prompt. There is no zero-click path,
   so the page must not claim one. The honest flow is: **install, approve,
   connect.**
5. **The SessionStart hook does NOT see userConfig defaults.**
   `CLAUDE_PLUGIN_OPTION_DIRECTUS_URL` is only populated once the user explicitly
   configures, so on a default install the hook prints "Muster: no board
   configured" even though the MCP server is connected and working. The hook
   fails quiet by design, so this is cosmetic, not broken. It is an inconsistency
   in how defaults reach MCP interpolation versus hook env, and it is a known
   gap, not a claim the page may make.
6. **The plugin's tools are the generic Directus MCP set** (`items`, `schema`,
   `files`, `folders`, `assets`, `trigger-flow`, `system-prompt`), not
   Muster-specific tools. Reading `os_tasks` is an `items` read. `trigger-flow`
   is inert against the demo board: `/flows` returns 403.

## Uninstall (this install was left in place)

```
claude plugin uninstall muster@muster
claude plugin marketplace remove muster
```
