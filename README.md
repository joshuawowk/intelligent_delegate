# intelligent_delegate

> Plugin id `intelligent-delegate` · repo/folder `intelligent_delegate`

A Claude Code plugin that answers three questions before work gets handed off:

1. **Should this be delegated at all?** — most of the available savings live here
2. **What shape?** — inline, one subagent, or a Workflow fan-out
3. **At what tier?** — which model, and which reasoning effort

It ships a `delegate` skill (the routing procedure), seven pre-tiered agent
definitions (the thing that makes an effort choice actually reachable), and a
`PreToolUse` hook that refuses a Workflow whose `agent()` calls carry no `agentType`.

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

## The seven tiers

| `subagent_type` | Model | Effort | Output cost | Use when |
|---|---|---|:---:|---|
| `mechanical` | haiku | — ¹ | **1×** | Fully specified, deterministic, verifiable without judgment |
| `worker` | sonnet | medium | **2×** | Ordinary implementation and research against a clear spec |
| `drafter` | sonnet | high | **2×** | **Default to generate** — an artifact from source you supply; **writes** |
| `inspector` | sonnet | high | **2×** | **Default to verify** — review, audit, per-item checks (no Edit/Write) |
| `reviewer` | inherit | high | *session* | **Escalation** above `inspector`: absence proofs, the gating verdict (no Edit/Write) |
| `builder` | inherit | high | *session* | **Escalation** above `drafter`: genuine ambiguity, silent-failure blast radius — **writes** |
| `judge` | opus | xhigh | **4–5×** | A contested call where being wrong is expensive (no Edit/Write) |

**Start at `drafter` / `inspector`, escalate on blast radius.** `reviewer` and `builder`
are `model: inherit` — in an Opus session they *are* Opus, so picking one is not a saving.
That is not a hypothetical: three measured fan-outs (2026-09-30 ×2, 2026-10-08 ×4 scripts)
ran 100% on Opus, and **two of them were passing `agentType` correctly**. The sonnet/high
pair added in 0.3.0 is the rung that was missing — the ladder used to jump from
sonnet/*medium* straight to the session model, so "more than `worker` deserves" had
nowhere to go but Opus.

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
  mechanical.md   worker.md                   # haiku, sonnet/medium
  drafter.md      inspector.md                # sonnet/high — the defaults
  reviewer.md     builder.md                  # model: inherit — the escalations
  judge.md                                    # opus/xhigh
hooks/
  hooks.json                      # PreToolUse on Workflow
  tier_check.py                   # denies agent() calls with no agentType
  test_tier_check.py              # 20 cases; run it directly
skills/delegate/
  SKILL.md                        # the routing procedure
  references/
    model-selection.md            # cost arithmetic, effort×model grid
    workflow-patterns.md          # fan-out shapes and per-stage tiering
    agent-catalog.md              # every subagent_type and what it costs
```

## The hook, and why a hook

Guidance in this repo told you to put `agentType` on every `agent()` call. It was correct,
it was specific, and it was ignored three times — including by a session with the skill
loaded, eleven days after the failure was written up in `workflow-patterns.md`.

So 0.3.0 stops asking. `hooks/tier_check.py` runs as `PreToolUse` on `Workflow`, lexes the
script, and **denies** the call if any `agent()` has no `agentType`, listing the line
numbers and the default tier for each stage kind.

Three properties worth knowing:

- **It lexes, it does not grep.** Workflow prompts discuss `agent()` constantly — this
  repo's own docs do — and a regex would block correct scripts. String bodies, template
  text and comments are not code. `subagent(` and `obj.agent(` are not matches.
- **It fails open.** Unparseable input, an unexpected payload shape, an internal error, a
  workflow invoked by saved `name` — all exit 0 and allow. A cost-control hook that wedges
  a legitimate run gets switched off, and then it protects nothing.
- **One escape hatch.** `effort: 'max'` is unreachable from frontmatter, so bare opts are
  sometimes right. Put `// untiered: <reason>` on or just above the call. The reason is the
  point: it costs one sentence of thought, which is all the check is buying.

It also emits a non-blocking note when every call is tiered but several use
`reviewer`/`builder`, since those inherit and are therefore an escalation rather than a
saving.

> **If a deny names a tier and that tier then errors as "not found", your session predates
> the upgrade.** Hit while building this release: a Workflow passing
> `agentType: 'intelligent-delegate:inspector'` failed with
> `agent type 'intelligent-delegate:inspector' not found. Available agents: … builder,
> judge, mechanical, reviewer, worker` — the pre-0.3.0 five. Agent definitions are
> registered at session start, so a session that began before `drafter` and `inspector`
> existed cannot address them, even though the files are on disk and a fresh session sees
> all seven. Restart, or `/reload-plugins`. The hook and the tiers normally load together,
> so this only bites in the session where you installed or edited the plugin — which is
> exactly the session where you are most likely to be testing it.

Tests: `python3 hooks/test_tier_check.py` — 20 cases, most of them guarding against a
false *deny*. It was also run against the four real workflow scripts from the 2026-10-08
incident and denies all four at the correct line numbers, with no false positives from
several hundred lines of embedded prompt text.

**Verified end-to-end, 2026-10-08**, because a hook that only works in unit tests is a
file, not a control. Three probes in fresh `claude -p` sessions against this checkout:

| probe | result |
|---|---|
| seven tiers registered | `intelligent-delegate:` + `builder drafter inspector judge mechanical reviewer worker` |
| untiered `agent()` | **blocked.** `PreToolUse:Workflow hook error: … 1 of 1 agent() calls … have no agentType`, followed by the stage-kind table. The script never ran. |
| correctly tiered `agent()` | **ran.** Not blocked; the agent returned. |
| all tiered but using `reviewer` | ran, and the non-blocking note **is** surfaced in the hook event stream (`--include-hook-events`) |

The last two were run with `--model haiku` so that `reviewer`'s `inherit` resolved to the
cheap tier — the probe costs pennies and still exercises the real path.

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

Skills, agent definitions and hooks are registered at session start, so **start a new
session** afterwards. Verify with `/plugin` — the seven agents should appear as
`intelligent-delegate:mechanical`, `:worker`, `:drafter`, `:inspector`, `:reviewer`,
`:builder`, and `:judge`.

To work on the plugin in place instead, point the marketplace at this checkout directly —
and know which copy a session actually loads, because there are two and only one matters.

**Resolved by probe, 2026-10-01: a local-path install loads in place from the checkout.** A
fresh `claude -p` session was asked to print the `Tools` line for
`intelligent-delegate:reviewer` and returned `(Tools: Read, Grep, Glob, Bash, ToolSearch)` —
a `ToolSearch` entry that existed only in the working tree, not in the cache copy. So:

- **New sessions are current automatically.** No reinstall, no version bump, no app restart.
  Edit the tree and the next session has it.
- **A session already running is not.** It holds the definitions it loaded at start. Restart it
  or `/reload-plugins`. This is the one that bites: a mid-session edit does not reach agents
  that session spawns, which is how a fix sitting in the tree truncated two audit agents at a
  `maxTurns` value it had already replaced.
- **`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/` and the recorded
  `gitCommitSha` are bookkeeping for a local-path install, not the live source.** That path
  contains `plugin.json`'s `version`, so neither moves until the version does — the cache can
  sit many commits behind while every new session runs current code. Do not read a stale
  `gitCommitSha` as "my edits are not live"; check a fresh session instead.
- **This does not generalise to a remote marketplace**, where the cached copy *is* what runs.
  There, bump the version and reinstall.

Bumping the `version` in `.claude-plugin/plugin.json` is still worth doing for a real release —
it is what lets the installer re-record, keeps `claude plugin details` honest, and is required
for anyone installing from the remote:

```bash
claude plugin marketplace update intelligent-delegate
claude plugin update intelligent-delegate@intelligent-delegate
```

`evals/measure_triggers.py` prints which copy it is measuring and reports cache drift without
blocking on it, since the `claude -p` sessions it spawns load the tree by construction.

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
