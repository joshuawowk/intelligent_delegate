# intelligent_delegate

A Claude Code plugin that answers three questions before work gets handed off:

1. **Should this be delegated at all?** — most of the available savings live here
2. **What shape?** — inline, one subagent, or a Workflow fan-out
3. **At what tier?** — which model, and which reasoning effort

It ships a `delegate` skill (the routing procedure) and four pre-tiered agent
definitions (the thing that makes an effort choice actually reachable).

## The constraint this plugin exists to solve

The `Agent` tool accepts `model` — `haiku | sonnet | opus | fable` — but it has
**no `effort` parameter**. Reasoning effort is only settable in two places:

| Where | `model` | `effort` |
|---|:---:|:---:|
| `Agent` tool | ✅ | ❌ |
| `Workflow` `agent(prompt, opts)` | ✅ | ✅ |
| Agent definition frontmatter (`agents/*.md`) | ✅ | ✅ |

(`SKILL.md` frontmatter is **not** a third lever. `effort:` there *is* honoured by the
harness, but it sets the invoking turn's effort — never a subagent's. It is also absent
from the published Agent Skills spec, which allows only `name`, `description`, `license`,
`allowed-tools`, `metadata`, and `compatibility`, so the official `skill-creator`
validator rejects it and the skill stops being portable.)

So advice like "run mechanical stages at low effort" is unexecutable from a plain
`Agent` call — unless someone has already shipped an agent definition with that
effort baked in. That is what `agents/` here is for. Pass one as `subagent_type`
and you get its model *and* its effort.

## The four tiers

| `subagent_type` | Model | Effort | Output cost | Use when |
|---|---|---|:---:|---|
| `mechanical` | haiku | low | **1×** | Fully specified, deterministic, verifiable without judgment |
| `worker` | sonnet | medium | **2×** | Ordinary implementation and research — the default |
| `reviewer` | inherit | high | *session* | Finding what is wrong (no Edit/Write) |
| `judge` | opus | xhigh | **4–5×** | A contested call where being wrong is expensive (no Edit/Write) |

Cost multipliers are output-token ratios against Haiku 4.5. `opus` is an alias that
resolves to your configured default Opus, and that spans two priced rows (Opus 5.5 at 4×,
Opus 5 at 5×) — hence the range. Fable 5.1 is 10× and
is deliberately not offered as a tier — see the skill body for when it is ever
worth it on a subagent.

`reviewer` inherits rather than pinning a model on purpose: finding defects
rewards *effort* far more than it rewards raw capability, so that tier raises
effort and leaves the model alone.

Plugin agents are namespaced — the full names are `intelligent_delegate:mechanical`,
`intelligent_delegate:worker`, and so on.

## Layout

```
.claude-plugin/
  plugin.json                   # the plugin manifest
  marketplace.json              # single-plugin marketplace, source "./"
agents/
  mechanical.md   worker.md   reviewer.md   judge.md
skills/delegate/
  SKILL.md                        # the routing procedure
  references/
    model-selection.md            # cost arithmetic, effort×model grid
    workflow-patterns.md          # fan-out shapes and per-stage tiering
    agent-catalog.md              # every subagent_type and what it costs
```

## Install

The repo is its own single-plugin marketplace (`.claude-plugin/marketplace.json`
with `source: "./"`), so it installs in two steps. Clone it:

```bash
git clone https://github.com/joshuawowk/intelligent_delegate.git ~/.claude/local-plugins/intelligent_delegate
```

Then, from an **interactive** `claude` session — these are terminal-dialog
commands and won't run in the desktop app's Code tab:

```
/plugin marketplace add ~/.claude/local-plugins/intelligent_delegate
/plugin install intelligent_delegate@intelligent_delegate
```

Skills and agent definitions are registered at session start, so **start a new
session** afterwards. Verify with `/plugin` — the four agents should appear as
`intelligent_delegate:mechanical`, `:worker`, `:reviewer`, and `:judge`.

To work on the plugin in place instead, point the marketplace at this checkout
directly and `git pull` to update; no reinstall needed, just a new session.

## Use

The skill loads on its own when a task involves delegation, parallelism, model
choice, or cost. You can also invoke it directly:

```
/intelligent_delegate:delegate
```

## License

MIT
