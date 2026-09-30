# intelligent-delegate

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
| `SKILL.md` frontmatter | ❌ | ✅ |

So advice like "run mechanical stages at low effort" is unexecutable from a plain
`Agent` call — unless someone has already shipped an agent definition with that
effort baked in. That is what `agents/` here is for. Pass one as `subagent_type`
and you get its model *and* its effort.

## The four tiers

| `subagent_type` | Model | Effort | Output cost | Use when |
|---|---|---|:---:|---|
| `mechanical` | haiku | low | **1×** | Fully specified, deterministic, verifiable without judgment |
| `worker` | sonnet | medium | **2×** | Ordinary implementation and research — the default |
| `reviewer` | inherit | high | *session* | Finding what is wrong (read-only) |
| `judge` | opus | xhigh | **5×** | A contested call where being wrong is expensive (read-only) |

Cost multipliers are output-token ratios against Haiku 4.5. Fable 5.1 is 10× and
is deliberately not offered as a tier — see the skill body for when it is ever
worth it on a subagent.

`reviewer` inherits rather than pinning a model on purpose: finding defects
rewards *effort* far more than it rewards raw capability, so that tier raises
effort and leaves the model alone.

Plugin agents are namespaced — the full names are `intelligent-delegate:mechanical`,
`intelligent-delegate:worker`, and so on.

## Layout

```
.claude-plugin/plugin.json
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

Clone it somewhere and add it as a local marketplace:

```bash
git clone https://github.com/joshuawowk/intelligent_delegate.git ~/.claude/local-plugins/intelligent-delegate
```

Then from an interactive `claude` session:

```
/plugin marketplace add ~/.claude/local-plugins/intelligent-delegate
```

Agent definitions and skills register at session start, so start a new session
after installing.

## Use

The skill loads on its own when a task involves delegation, parallelism, model
choice, or cost. You can also invoke it directly:

```
/intelligent-delegate:delegate
```

## License

MIT
