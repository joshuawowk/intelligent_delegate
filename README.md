# intelligent_delegate

> Plugin id `intelligent-delegate` · repo/folder `intelligent_delegate`

A Claude Code plugin that answers three questions before work gets handed off:

1. **Should this be delegated at all?** — most of the available savings live here
2. **What shape?** — inline, one subagent, or a Workflow fan-out
3. **At what tier?** — which model, and which reasoning effort

It ships a `delegate` skill (the routing procedure) and five pre-tiered agent
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

## The five tiers

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
> inverts the saving you pinned the tier for. The controls are session-wide —
> `/advisor off`, or `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`. Per-agent suppression is
> impossible: the advisor is server-side and never reaches an agent's tool filter.

Cost multipliers are output-token ratios against Haiku 4.5. `opus` is an alias that
resolves to your configured default Opus, and that spans two priced rows (Opus 5.5 at 4×,
Opus 5 at 5×) — hence the range. Fable 5.1 is 10× and
is deliberately not offered as a tier — see the skill body for when it is ever
worth it on a subagent.

`reviewer` inherits rather than pinning a model on purpose: finding defects
rewards *effort* far more than it rewards raw capability, so that tier raises
effort and leaves the model alone.

Plugin agents are namespaced — the full names are `intelligent-delegate:mechanical`,
`intelligent-delegate:worker`, and so on.

## Layout

```
.claude-plugin/
  plugin.json                   # the plugin manifest
  marketplace.json              # single-plugin marketplace, source "./"
agents/
  mechanical.md   worker.md   reviewer.md   builder.md   judge.md
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
/plugin install intelligent-delegate@intelligent-delegate
```

Skills and agent definitions are registered at session start, so **start a new
session** afterwards. Verify with `/plugin` — the five agents should appear as
`intelligent-delegate:mechanical`, `:worker`, `:reviewer`, `:builder`, and `:judge`.

To work on the plugin in place instead, point the marketplace at this checkout directly.
**But do not expect edits to go live on their own.** The install is a *copy* under
`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, and the cache path is keyed on
the `version` in `.claude-plugin/plugin.json`. While that version string does not change,
`git pull` and local edits leave the cache untouched — measured here, the install sat six
commits behind the working tree, still serving the previous `maxTurns` values, and agents
spawned from it ran the old caps. A new session does not fix it.

**Bumping the `version` in `.claude-plugin/plugin.json` is what makes a refresh possible** —
the cache path contains it, so a new version is a new directory. Treat the version as part
of the release step for any change you expect to take effect, not as cosmetic metadata.

To actually pick up changes, do one of:

```bash
# reinstall over the stale copy
claude plugin install intelligent-delegate@intelligent-delegate --force
# or verify what is actually installed before trusting a measurement
python3 -c "import json;d=json.load(open('$HOME/.claude/plugins/installed_plugins.json'));print(json.dumps(d,indent=1))" | grep -A2 installPath
```

`evals/measure_triggers.py` now compares the installed commit against `git rev-parse HEAD`
and refuses to run on a mismatch, because an eval against a stale install measures the
wrong plugin and says nothing about your edits.

### Verified install

Non-interactive equivalents exist and were used to verify this repo:

```bash
claude plugin validate .
claude plugin marketplace add /path/to/intelligent_delegate
claude plugin install intelligent-delegate@intelligent-delegate
claude plugin details intelligent-delegate@intelligent-delegate
```

`details` reports the registered inventory — **1 skill, 5 agents** — and a token cost.
**Measured 2026-09-30 at commit `d2ba47d`: ~1,016 tokens always-on, ~5.1k when the
`delegate` skill fires, ~570–740 per agent invocation.** Treat all three as stale: `SKILL.md`
has grown since, so skill-load is now nearer 6–7k by this repo's own ÷4 rule, and no
`details` output is archived here. Re-run `details` after editing rather than quoting these.

> **Note on names.** The plugin id is `intelligent-delegate` (kebab-case, so
> `claude plugin validate` passes clean and it can sync to claude.ai). The **repo and
> folder** are `intelligent_delegate` with an underscore. The mismatch is deliberate:
> the plugin id is what shows up in `/plugin` and in agent namespaces; the folder name
> is just where it lives on disk.

## Use

The skill loads on its own when a task involves delegation, parallelism, model
choice, or cost. You can also invoke it directly:

```
/intelligent-delegate:delegate
```

## License

MIT
