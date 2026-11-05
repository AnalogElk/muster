# Verified install (do not paraphrase)

Install strings verified **2026-07-15** against `github.com/AnalogElk/muster` @
`340d721`, from a clean temp directory, on Claude Code 2.1.211. The configuration
behavior was re-verified **2026-11-05** on Claude Code 2.1.318, after the default
board was removed. These exact strings are what the homepage hero must use.
Everything below was observed, not read in a doc.

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

## Configuration is required

Muster has no default board. A board URL and a Directus API token are required
from the user. The public demo is a static snapshot and cannot be connected to.

```
$ claude plugin install muster@muster
2 userConfig options not yet set (2 required) — run /plugin configure muster@muster in Claude Code, or pass --config KEY=VALUE.

$ claude mcp get plugin:muster:muster-board
No MCP server named "plugin:muster:muster-board". Run `claude mcp add` to add one.
```

The MCP server does not exist until both values are set.

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
2. **There is no default board.** `directus_url` and `directus_token` are both
   required and have no default. Until the user sets them, the MCP server is not
   registered, so `/muster:connect` stops and asks for them.
3. **The MCP server's real name is `plugin:muster:muster-board`**, not
   `muster-board`. Plugin MCP servers are namespaced `plugin:<plugin>:<server>`,
   and its tools are `mcp__plugin_muster_muster-board__*`.
4. **First use of an MCP tool needs a one-time permission grant.** In an
   interactive session the user approves a prompt. There is no zero-click path,
   so the page must not claim one. The honest flow is: **install, configure,
   approve, connect.**
5. **The SessionStart hook reads the configured values.** Until the user sets
   them, it prints "Muster: no board configured" and exits 0. It fails quiet by
   design.
6. **The plugin's tools are the generic Directus MCP set** (`items`, `schema`,
   `files`, `folders`, `assets`, `trigger-flow`, `system-prompt`), not
   Muster-specific tools. Reading `os_tasks` is an `items` read.

## Uninstall (this install was left in place)

```
claude plugin uninstall muster@muster
claude plugin marketplace remove muster
```
