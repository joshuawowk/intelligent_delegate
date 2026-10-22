# intelligent_delegate

[![Release](https://img.shields.io/github/v/release/joshuawowk/intelligent_delegate?include_prereleases&sort=semver)](https://github.com/joshuawowk/intelligent_delegate/releases)
[![License: MIT](https://img.shields.io/github/license/joshuawowk/intelligent_delegate)](LICENSE)

> Plugin id `intelligent-delegate` · repo/folder `intelligent_delegate`

A Claude Code plugin that answers three questions before work gets handed off, aiming at
speed, result quality and cost together:

1. **Should this be delegated at all?** — a hand-off has overhead in time and tokens, so
   the first question is whether it pays
2. **What shape?** — inline, one subagent, or a Workflow fan-out
3. **At what tier?** — which model, and which reasoning effort

It ships a `delegate` skill (the routing procedure), eight pre-tiered agent definitions
(each bundles a model, an effort, a tool allowlist and a turn cap), a `PreToolUse`
hook that refuses a Workflow whose `agent()` calls carry no `agentType`, and an audit
script — `scripts/delegation_audit.py`, or `/intelligent-delegate:audit` — that splits a
session's spend into the orchestrator and each subagent.

**What 0.5.0 found.** The first real sessions audited after 0.4.0 tiered every subagent
correctly — and the Opus orchestrator was still 74-76% of the bill, from re-reading its own
large context on every request and on every background-agent completion. The skill now
treats the orchestrator as a cost centre, and its facts were re-checked against the
2026-10-22 Anthropic docs (see `CHANGELOG.md`).

## The constraint this plugin exists to solve

A subagent that names no effort runs at the **session's** effort, not at a default. Every
tier here pins one. An `agent()` or `Agent` call that names no tier inherits the
session's model **and** its effort: in an Opus session at `xhigh` that measured 6.2x the
time and 6.6x the cost of `sonnet/medium` for the same score. And only an agent
definition can set `tools`, `maxTurns` and `omitClaudeMd` — a bare call loses those, the
operating rules and the return-value contract.

| Where | `model` | `effort` | `tools`, `maxTurns`, `omitClaudeMd` |
|---|:---:|:---:|:---:|
| `Agent` tool call | ✅ | ✅ | ❌ |
| `Workflow` `agent(prompt, opts)` | ✅ | ✅ | ❌ |
| Agent definition frontmatter (`agents/*.md`) | ✅ | ✅ | ✅ |

Pass a tier as `subagent_type` and you get its model *and* its effort. Call-site `effort`
beats the definition's, which beats the session's (probed 2026-10-09). The `Agent` tool's
own rule is to set `effort` only when a user or a skill asks; this skill asks. Pass
`effort: 'high'` on the call before you reach for a different tier; change tier on an
escalation predicate, not on a feeling. (`SKILL.md`'s own `effort:` sets the invoking turn.)

## The eight tiers

| `subagent_type` | Model | Effort | Price | Measured | Use when |
|---|---|---|:---:|---|---|
| `mechanical` | haiku | low | **1x** | 18.3 s, $0.0041 | Fully specified, deterministic, verifiable without judgment; **writes** |
| `scout` | haiku | low | **1x** | 18.3 s, $0.0041 | Pull named facts out of a large input when you can check the answer (read-only) |
| `worker` | sonnet | medium | **20x** | 14.0 s, $0.0441 | Ordinary implementation and research against a clear spec |
| `drafter` | sonnet | high | **20x** | 21.6 s, $0.0586 | **Default to generate** — an artifact from source you supply; **writes** |
| `inspector` | sonnet | medium | **20x** | 14.0 s, $0.0441 | **Default to verify** — review, audit, per-item checks (no Edit/Write) |
| `reviewer` | inherit | high | *session* | 41.7 s, $0.1672 | **Escalation** above `inspector`: absence proofs, the gating verdict (no Edit/Write) |
| `builder` | inherit | high | *session* | 41.7 s, $0.1672 | **Escalation** above `drafter`: genuine ambiguity, silent-failure blast radius — **writes** |
| `judge` | opus | xhigh | **40x** | 86.2 s, $0.2923 | A contested call where being wrong is expensive (no Edit/Write) |

Price is Haiku 1x / Sonnet 20x / Opus 40x / Fable 100x, input and output alike.
**Measured** is the mean of four tasks from the 2026-10-09 sweep (240 runs, Claude Code
2.1.295, an `opus/xhigh` session, none void): the model-and-effort *cell*, not the tier
file, since the sweep borrowed `worker`'s and `inspector`'s definitions. `reviewer` and
`builder` show `opus/high`, what they are in an Opus session; `judge` was not measured as
a tier. 47 of 48 task-by-arm cells scored 0.98 or better, so the sweep ranks cells on time
and money and says little about which is smarter.

**Start at `drafter` / `inspector`, escalate on blast radius.** `reviewer` and `builder`
are `model: inherit` — in an Opus session they *are* Opus: an escalation in capability,
time and cost, chosen for the result. That is not a hypothetical: three measured fan-outs (2026-09-30 ×2, 2026-10-08 ×4 scripts) ran 100% on Opus
(`claude-opus-5`). **One of them was passing `agentType` correctly throughout** — the
19-agent 2026-09-30 run — and a second was doing so on 5 of its 13 calls (the 81-agent run
passed none, so only one is a clean case). The `drafter`/`inspector` pair is the rung that
was missing: the ladder used to jump from `worker` straight to the session model, so "more
than `worker` deserves" had nowhere to go but Opus.

`inspector` runs at `medium`: on a seeded-defect review it was 39% faster than at `high`
with every defect found in every run. That task was **saturated** — `medium` is enough
for a bounded check; nothing here speaks to harder review. For more thoroughness, pass
`effort: 'high'` on the call before reaching for `reviewer`.

**Haiku 5.5 takes an effort setting** (Haiku 4.5 took none), so `mechanical` and `scout`
pin `low`: an unpinned tier would inherit the session's, and `haiku/xhigh` took 31.8 s on
the transform task where `haiku/low` took 12.9 s — 2.5x slower for the same score. Haiku
is the cheap model, not the fast one: it measured 1.6x slower than Sonnet at `medium`.
It is 20x cheaper on price, about 10x measured — Haiku writes about three times the
output tokens. Haiku 5.5 has a 1M window; above 100K prompt tokens it bills 5x its base
rate, which is still a quarter of Sonnet's. `scout` qualified on cost, not speed: on the
extraction task `haiku/low` took 10.7 s and $0.0027 and got 48 of 50 answers, where every
Sonnet and Opus run got all of them; both misses were the line *after* a named entry.
That run used `inspector`'s definition: the figures describe Haiku at `low` on this
work, not `scout`'s own narrower surface.

> **The price ladder is a floor, not a ceiling.** If an advisor is configured for the
> session (`/advisor`), *every* subagent is given it — measured here as
> `claude-fable-5-1`, the 100x tier on price, injected even into `mechanical`. A consult is
> Fable work, so on a Haiku tier one can outweigh the run; its latency and cost when
> consulted were not measured (attached to all 240 sweep runs, called by none). Controls
> are session-wide — `/advisor off`, or `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1`; per-agent
> suppression is impossible, as the advisor is server-side and skips the tool filter.

The aliases resolve to `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` and
`claude-fable-5-1`; Fable is deliberately not offered as a tier (the skill body says when
it is ever worth it). `reviewer` inherits rather than pinning a model on purpose: finding
defects rewards *effort* more than raw capability (judged, not measured).

## Layout

```
.claude-plugin/
  plugin.json  marketplace.json # manifest; single-plugin marketplace, source "./"
agents/
  mechanical.md   scout.md        # haiku/low
  worker.md       inspector.md    # sonnet/medium
  drafter.md      judge.md        # sonnet/high; opus/xhigh
  reviewer.md     builder.md      # model: inherit — the escalations
hooks/
  hooks.json                      # PreToolUse on Workflow, Agent and Task
  tier_check.py                   # denies agent() calls with no agentType; notes the rest
  test_tier_check.py              # 64 cases; run it directly
scripts/
  delegation_audit.py             # orchestrator vs subagent spend for one session
  test_delegation_audit.py        # 24 checks on a synthetic transcript
skills/delegate/
  SKILL.md                        # the routing procedure
  references/
    orchestrator-cost.md          # what the main loop costs, and the levers
    model-selection.md            # prices, the measured grid, platform features
    workflow-patterns.md          # fan-out shapes and per-stage tiering
    agent-catalog.md              # every subagent_type and when to use it
skills/audit/
  SKILL.md                        # /intelligent-delegate:audit (user-invoked only)
CHANGELOG.md                      # what changed in each release
```

## The hook, and why a hook

Guidance in this repo told you to put `agentType` on every `agent()` call. It was correct,
it was specific, and it was ignored three times — including by a session with the skill
loaded, **seven days** after the failure was written up in `workflow-patterns.md`
(commit `279aa14`, 2026-10-01; recurrence 2026-10-08).

So 0.3.0 stopped asking. `hooks/tier_check.py` runs as `PreToolUse` on `Workflow`, lexes the
script, and **denies** the call if any `agent()` has no `agentType`, listing the line
numbers and the default tier for each stage kind.

Three properties worth knowing:

- **It lexes, it does not grep.** Workflow prompts discuss `agent()` constantly — this
  repo's own docs do — and a regex would block correct scripts. String bodies, template
  text and comments are not code. `subagent(` and `obj.agent(` are not matches.
- **It fails open.** Unparseable input, an unexpected payload shape, an internal error, a
  workflow invoked by saved `name` — all exit 0 and allow. A hook that wedges a legitimate
  run gets switched off, and then it protects nothing.
- **One escape hatch.** Bare opts are sometimes right. Put `// untiered: <reason>` on or
  just above the call; the reason costs one sentence of thought, which is all the check is
  buying. A waived call that names no `effort` draws a warning: it would run at the
  session's.

It also notes, without blocking, when any tiered call uses `reviewer`/`builder` (they
inherit, so they escalate in capability and cost) and when a call could not be checked at
all, so an unchecked call is never mistaken for a checked one.

Since 0.5.0 it also notes an `Agent` call that names no tier and no model, and warns once
per session when `CLAUDE_CODE_EFFORT_LEVEL` or `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` is set —
either one overrides every tier's pin. Notes now go out as `additionalContext` as well as
`systemMessage`: the hooks docs say `systemMessage` is shown to the user only, so before
0.5.0 the orchestrator never read them.

> **If a deny names a tier and that tier then errors as "not found", your session predates
> the upgrade.** Hit while building 0.3.0: a Workflow passing
> `agentType: 'intelligent-delegate:inspector'` failed with
> `agent type 'intelligent-delegate:inspector' not found. Available agents: … builder,
> judge, mechanical, reviewer, worker` — the pre-0.3.0 five. Agent definitions are
> registered at session start, so a session that began before a tier existed cannot
> address it. Restart, or `/reload-plugins`. This only bites in the session where you
> installed or edited the plugin — exactly the one where you are most likely testing it.

Tests: `python3 hooks/test_tier_check.py` — 64 cases. The 0.3.0 suite also denied all four
real workflow scripts from the 2026-10-08 incident at the correct line numbers, with no
false positives from several hundred lines of embedded prompt text.

**Verified end-to-end, 2026-10-09**, because a hook that only works in unit tests is a
file, not a control, and a tier whose frontmatter says `low` has proved nothing until one
runs at `low`. Both checks are scripts. Each starts fresh `claude -p --plugin-dir <this
repo>` sessions and reads what the harness recorded, never what a model said, and each has
a `--self-test` showing that its comparison can fail.

| `evals/probe_tiers.py` | parent | declared | ran as |
|---|---|---|---|
| `mechanical`, `scout` | sonnet / max | haiku / low | `claude-haiku-5-5` at `low` |
| `worker`, `inspector` | haiku / max | sonnet / medium | `claude-sonnet-5-5` at `medium` |
| `drafter` | haiku / max | sonnet / high | `claude-sonnet-5-5` at `high` |
| `reviewer`, `builder` | haiku / max | inherit / high | `claude-haiku-5-5` (the parent's) at `high` |
| `judge` | haiku / max | opus / xhigh | `claude-opus-5-5` at `xhigh` |

**8 of 8 ran as declared.** The parent is chosen so that a lost pin cannot pass by
inheriting the same value: it runs at `max`, which no tier pins, and on a model the tier
does not pin. A tier that declares no effort at all is a mismatch outright — that is how
`mechanical` ran before 0.4.0, at whatever the session was at.

| `evals/probe_hook.py` | what the hook returned | did an agent run |
|---|---|:--:|
| untiered `agent()` | **deny**, with the reason and the stage table | no |
| correctly tiered `agent()` | nothing | yes |
| tiered, on `reviewer` | the inherit note | yes |
| waived, with no `effort` named | the unset-effort warning | yes |

**4 of 4 behaved.** The decision is parsed from the hook's own output in the session's
`hook_response` event, and "ran" means a subagent transcript exists for that session.

Each session's init event names the path it loaded the plugin from, and both scripts fail
a case that loaded any other copy. That matters on a machine where the installed plugin is
a synced copy: see "Install". (0.3.0 recorded four hand-run probes on 2026-10-08 that
found the same first three hook results for its seven tiers.)

Two limits on what a reader can check from the repo alone. The four incident scripts are
**not committed here**, so "denies all four at the correct line numbers" is reproducible
by the author and not by you — a claim, not a verifiable one. And the probes confirm the
hook *loads and fires*; whether its recommended tiers produce better output the 2026-10-09
sweep measured for bounded work only, and nothing here measures it for work with a blast
radius, an unstated invariant or an absence to prove.

## Install

From an interactive `claude` session (the repo is its own single-plugin marketplace):

```
/plugin marketplace add joshuawowk/intelligent_delegate
/plugin install intelligent-delegate@intelligent-delegate
```

Start a new session afterwards. Requires `python3` on `PATH` for the Workflow-tier hook.
To install from a local clone instead, see below.

### Install from a local clone

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
session** afterwards. Verify with `/plugin` — the eight agents appear as
`intelligent-delegate:` + `mechanical`, `scout`, `worker`, `drafter`, `inspector`,
`reviewer`, `builder` and `judge`.

To work on the plugin in place instead, point the marketplace at this checkout directly —
and know which copy a session actually loads, because there are two and only one matters.
**An install may be a synced copy, which does not load the working tree.** On the machine
that ran the 2026-10-09 probes, `claude plugin list` reported `intelligent-delegate@synced`,
loaded from `~/.claude/plugins/synced/<id>/intelligent-delegate` — a copy the sync process
writes — and a new session did **not** pick up working-tree edits. Check with
`claude plugin list`; verify a changed definition in a session that loads the checkout
explicitly, `claude -p --plugin-dir <repo>`, which registers the tiers once, not twice.

**Resolved by probe, 2026-10-01: a local-path install loads in place from the checkout.** A
fresh `claude -p` session was asked to print the `Tools` line for
`intelligent-delegate:reviewer` and returned `(Tools: Read, Grep, Glob, Bash, ToolSearch)` —
a `ToolSearch` entry that existed only in the working tree, not in the cache copy. So, for
a local-path install:

- **New sessions are current automatically.** No reinstall, no version bump, no app restart.
- **A session already running is not.** It holds the definitions it loaded at start. Restart it
  or `/reload-plugins`. This is the one that bites: a mid-session edit does not reach agents
  that session spawns, which is how a fix sitting in the tree truncated two audit agents at a
  `maxTurns` value it had already replaced.
- **The `~/.claude/plugins/cache/.../<version>/` copy and the recorded `gitCommitSha` are
  bookkeeping for a local-path install, not the live source.** Neither moves until the
  version does; do not read a stale `gitCommitSha` as "my edits are not live".
- **This does not generalise to a remote marketplace or a synced copy**, where the cached
  copy *is* what runs. There, bump the version and reinstall.

Bump the `version` in `.claude-plugin/plugin.json` for a real release — it lets the
installer re-record, keeps `claude plugin details` honest, and remote installs need it —
then `claude plugin marketplace update intelligent-delegate` and
`claude plugin update intelligent-delegate@intelligent-delegate`.

`evals/measure_triggers.py` does not rely on any of this: it passes `--plugin-dir` on every
call and fails any call whose own init event names another copy.

### Verified install

Non-interactive equivalents exist and were used to verify this repo: `claude plugin
validate .`, then `marketplace add <path>`, `install` and `details
intelligent-delegate@intelligent-delegate`.

`details` reports the registered inventory — **1 skill, 8 agents** — and a token cost.
**Measured 2026-09-30 at commit `d2ba47d`: ~1,016 tokens always-on, ~5.1k when the
`delegate` skill fires, ~570–740 per agent invocation.** Treat all three as stale: no
`details` output is archived here. Re-run `details` after editing rather than quoting these.

> **Note on names.** The plugin id is `intelligent-delegate` (kebab-case, so
> `claude plugin validate` passes clean and it can sync to claude.ai); the **repo and
> folder** are `intelligent_delegate`. The mismatch is deliberate: the id is what shows up
> in `/plugin` and in agent namespaces (`intelligent-delegate:worker`).

## Use

The skill loads on its own when a task involves delegation, parallelism, model
choice, speed or cost. You can also invoke it directly: `/intelligent-delegate:delegate`.

To see where a session's money went, run `/intelligent-delegate:audit` (user-invoked, so it
costs nothing in the skill listing), or directly:

```
python3 scripts/delegation_audit.py                 # newest transcript under ~/.claude/projects
python3 scripts/delegation_audit.py <session-id> --json
```

## License

MIT
