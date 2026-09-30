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
| `mechanical` | haiku | — ¹ | **1×** | Fully specified, deterministic, verifiable without judgment |
| `worker` | sonnet | medium | **2×** | Ordinary implementation and research — the default |
| `reviewer` | inherit | high | *session* | Finding what is wrong (no Edit/Write) |
| `builder` | inherit | high | *session* | Implementation needing judgment — **writes** |
| `judge` | opus | xhigh | **4–5×** | A contested call where being wrong is expensive (no Edit/Write) |

¹ **Haiku 4.5 accepts no reasoning-effort setting** — the harness drops it and the
transcripts record none, so `mechanical` deliberately ships without an `effort:` line
rather than carry a knob that does nothing.

> **The multipliers are a floor, not a ceiling.** If an advisor is configured for the
> session (`/advisor`), *every* subagent is given it — measured here as
> `claude-fable-5-1`, the 10× tier, injected even into `mechanical`. One advisor consult
> inverts the saving you pinned the tier for. `/advisor off` is the reliable control;
> per-agent `disallowedTools` is untested against it.

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

### Verified install

Non-interactive equivalents exist and were used to verify this repo:

```bash
claude plugin validate .
claude plugin marketplace add /path/to/intelligent_delegate
claude plugin install intelligent_delegate@intelligent_delegate
claude plugin details intelligent_delegate@intelligent_delegate
```

`details` reports the registered inventory — **1 skill, 4 agents** — and the
token cost: **~762 tokens always-on**, plus ~5.1k when the `delegate` skill
actually fires and ~570–740 per agent invocation.

> **Known warning.** `claude plugin validate` flags `intelligent_delegate` as not
> kebab-case: *"Claude Code accepts it, but the Claude.ai marketplace sync
> requires kebab-case."* The underscore matches the repo and folder, so it stays.
> If you ever want to sync this to claude.ai, rename the plugin to
> `intelligent-delegate` in both `.claude-plugin/*.json` and update the
> `intelligent_delegate:` namespace references in the docs.

## Use

The skill loads on its own when a task involves delegation, parallelism, model
choice, or cost. You can also invoke it directly:

```
/intelligent_delegate:delegate
```

## License

MIT
