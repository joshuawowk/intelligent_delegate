# Model and effort selection

Read this when a tier call is genuinely close — the skill body handles the easy cases; this
file gives the hard ones their numbers: speed, result quality and cost, together.

## Contents

- Cost table
- Worked spend: a 10-agent fan-out
- The measured grid
- "Best model at lower effort" vs a multi-model cascade
- Cost per completed task, not per request
- The 100K price cliff
- The tool surface is the biggest lever
- Two things that break the table above
- Reaching MCP tools from a tier, and reading the error when you cannot
- How to set each knob
- Platform features checked 2026-10-22, and whether they reach Claude Code

## Cost table

First-party API rates, USD per million tokens. Read 2026-10-22 from the prompt-caching
pricing table on platform.claude.com; the model ids and context windows were read 2026-10-09
from the model catalog in Claude Code 2.1.295 (evidence: `evals/facts-2026-10-09.md`). The
default-effort column is from the Claude Code docs, model-config, read 2026-10-22. Re-verify
before quoting; a stale row here rots every derived ratio in this repo.

| Model | id | Context | In | 5m write | 1h write | Cache read | Out | Price ratio | Claude Code default effort |
|---|---|--:|--:|--:|--:|--:|--:|:--:|:--:|
| Haiku 5.5 (prompt ≤ 100K) | `claude-haiku-5-5` | 1M | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 | **1x** | medium |
| Haiku 5.5 (prompt > 100K) | | | $0.50 | $0.625 | $1.00 | $0.05 | $2.50 | 5x | |
| Sonnet 5.5 | `claude-sonnet-5-5` | 1M | $2 | $2.50 | $4 | $0.10 | $10 | **20x** | medium |
| Opus 5.5 | `claude-opus-5-5` | 1M | $4 | $5 | $8 | $0.20 | $20 | **40x** | medium |
| Fable 5.1 | `claude-fable-5-1` | 1M | $10 | $12.50 | $20 | $0.25 | $50 | **100x** | high |

The number to reason with is the price ladder: **Haiku 1x / Sonnet 20x / Opus 40x / Fable
100x, input and output alike.** That is *price*. For Haiku against Sonnet, say which: **20x
on price, about 10x measured — Haiku writes about three times the output tokens.** Each alias
resolves to exactly one row. Haiku 5.5 has a 1M window. Above 100K prompt tokens it bills 5x
its base rate, which is still a quarter of Sonnet's. The Claude Code default effort is
**not** what a subagent gets (it gets the session's unless the definition or call pins one);
see "How to set each knob".

**Cache reads are not uniformly 0.1x input.** Haiku 5.5 bills the standard **0.10x** of its
input rate; Opus 5.5 and Sonnet 5.5 bill **0.05x**; Fable 5.1 bills **0.025x** — cheaper,
not dearer (the catalog's `cache_read_0_20` / `cache_read_0_25` suffixes are dollar rates,
not multipliers). On a model priced by prompt length (Haiku 5.5), cache reads and writes
count toward the prompt length. The 1h write column is 2x input and the 5m column 1.25x
(prompt-caching pricing table, read 2026-10-22). This matters wherever input dominates, and
it softens the advisor argument below: a Fable advisor's *cached* input costs a quarter of
the usual fraction.

Cross-check, computed by Claude Code itself: in a real 2026-10-22 session it reported Sonnet
5.5 usage of 15.63M cache-read, 660K cache-write (5m) and 208K output tokens as **$5.29**,
which these rates reproduce exactly (1.563 + 1.65 + 2.08).

## Worked spend: a 10-agent fan-out

Assumptions, stated so you can substitute your own:

- 10 agents, one task each, all cold starts (subagents never inherit conversation)
- each agent **~40K input** (CLAUDE.md + system + task prompt + reads and tool results
  accumulated over the run) and **~5K output** → 400K in, 50K out

```
batch $ = (400K/1M x in_rate) + (50K/1M x out_rate)
```

| All 10 on | Input $ | Output $ | **Batch $** | Per agent $ |
|---|--:|--:|--:|--:|
| Haiku 5.5 | 0.04 | 0.025 | **0.065** | 0.0065 |
| Sonnet 5.5 | 0.80 | 0.50 | **1.30** | 0.13 |
| Opus 5.5 | 1.60 | 1.00 | **2.60** | 0.26 |
| Fable 5.1 | 4.00 | 2.50 | **6.50** | 0.65 |

Two things fall out that guessing does not give you. **Input dominates for tool-using
agents** — at 8:1 in:out, 62% of the bill is input, so between Sonnet and Opus narrowing what
each agent reads moves the number more than the tier does; between Haiku and Sonnet the tier
moves it more. And **the absolute numbers are small**: a ten-way Opus fan-out is $2.60, so
decide first whether it happens at all, then pick the tier on time and quality as well.

## The measured grid

Rows are model x effort. Measured 2026-10-09 on Claude Code 2.1.295 from an `opus/xhigh`
session: 240 runs, none void — 12 arms x 4 bounded tasks x 5 reps, each figure the mean of
the four per-task means. Per-task tables and every miss: `evals/tier-sweep/RESULTS.md`.

| arm | score | seconds | cost $ | output tokens | time vs own `high` | cost vs own `high` | what lands here |
|---|--:|--:|--:|--:|--:|--:|---|
| `haiku/low` | 0.988 | 18.3 | 0.0041 | 4365 | 0.59 | 0.67 | `mechanical`, `scout` |
| `haiku/medium` | 0.995 | 22.0 | 0.0046 | 5007 | 0.71 | 0.74 | |
| `haiku/high` | 0.995 | 30.9 | 0.0062 | 7112 | 1.00 | 1.00 | |
| `haiku/xhigh` | 1.000 | 64.0 | 0.0116 | 15235 | 2.07 | 1.86 | an unpinned Haiku agent in an `xhigh` session |
| `sonnet/low` | 0.998 | 12.8 | 0.0405 | 1374 | 0.59 | 0.69 | |
| `sonnet/medium` | 1.000 | 14.0 | 0.0441 | 1602 | 0.65 | 0.75 | `worker`, `inspector` |
| `sonnet/high` | 1.000 | 21.6 | 0.0586 | 2384 | 1.00 | 1.00 | `drafter`; `inspector` with `effort: 'high'` on the call |
| `sonnet/xhigh` | 1.000 | 51.7 | 0.1086 | 5823 | 2.39 | 1.85 | |
| `opus/low` | 0.998 | 20.0 | 0.0986 | 2101 | 0.48 | 0.59 | |
| `opus/medium` | 1.000 | 22.0 | 0.1066 | 2297 | 0.53 | 0.64 | |
| `opus/high` | 1.000 | 41.7 | 0.1672 | 4420 | 1.00 | 1.00 | `reviewer`, `builder` in an Opus session |
| `opus/xhigh` | 1.000 | 86.2 | 0.2923 | 9164 | 2.07 | 1.75 | `judge`; an untiered call from an `opus/xhigh` session |

**Read the score column as a ceiling, not a ranking.** 47 of 48 task x arm cells scored 0.98
or better. Measured on a saturated task: it shows the cheaper cell is enough for work of this
difficulty and nothing about harder work. Not measured: `max` effort, Fable, any task with a
blast radius, an unstated invariant or an absence to prove, and `judge` as a tier, on
adjudication (its `opus/xhigh` cell is the last row above).

- **`medium` is the default for bounded work on every model.** `low` saved 8-17% and is where
  every Sonnet and Opus miss happened; `high` took 1.4-1.9x as long and `xhigh` 2.9-3.9x, and
  neither improved a score.
- **Haiku is the cheap model, not the fast one:** at `medium` it took 1.6x as long as Sonnet
  and measured 9.5x cheaper (20x on price), on 3.1x the output tokens.
- **Opus bought nothing on bounded work:** at `medium`, 1.6x the time and 2.4x the cost of
  Sonnet for the same score. An untiered call inherits the session's model **and** its
  effort: in an Opus session at `xhigh` that measured 6.2x the time and 6.6x the cost of
  `sonnet/medium`, same score.

**The effort-cost index is retired.** The `effort_cost_index` this section used to multiply
prices by described Sonnet 5 and Opus 5, which the aliases no longer reach. Haiku 5.5, Sonnet
5.5 and Opus 5.5 are each *(no index published)*; Fable 5.1 publishes one (0.75 / 0.86 / 1 /
1.38 / 1.74, `low` to `max`). What replaces it is the two `vs own high` columns above: a
measurement on four tasks, not a constant. The old arithmetic called `sonnet/xhigh` against
`opus/high` a wash; measured, Sonnet at `xhigh` is cheaper and slower, and both are far
behind `sonnet/medium`. Cells to stay out of:

- **haiku @ xhigh, by inheritance.** `haiku/xhigh` took 3.5x the time and 2.8x the cost of
  `haiku/low`, so both Haiku tiers pin `low`. Raising Haiku's effort buys exactness
  (extraction task: 48 of 50 answers at `low`, 100 of 100 at `high` and `xhigh`), not speed:
  at `high` it took 24.1 s where `sonnet/medium` took 11.9 s on that extraction task.
- **fable @ low / medium, opus @ low.** Paying for the strongest available reasoning and then
  capping it. Fable is only defensible at high or xhigh, on a task where opus @ xhigh has
  already been tried and was not good enough (judged, not measured). `opus/low` was 9% faster
  than `opus/medium` and is where Opus's only miss happened.
- **`reviewer` and `builder` are `inherit` @ high** on purpose: they are the escalation
  rungs, so their cell moves with the session model. **The corollary is a trap in cost and in
  time:** on an Opus session every inherit tier — `reviewer`, `builder` — runs at Opus rates,
  so choosing one of them saves nothing. Selecting a tier feels like a cost decision and is
  not one. Measured 2026-09-30: a 19-agent fan-out passed
  `agentType: 'intelligent-delegate:reviewer'` on all 18 of its review and inventory calls
  (the 19th was the `judge` consolidation stage, which pins Opus regardless) and ran 19/19 on
  `claude-opus-5`; a sibling 81-agent run that passed no `agentType` at all produced the
  identical all-Opus outcome. Correct tier usage and no tier usage cost the same. It happened
  a third time on 2026-10-08, across four scripts — see `workflow-patterns.md` → "The turn
  cap is the constraint that decides this".
  (Those sessions ran `claude-opus-5`; `opus` now resolves to `claude-opus-5-5`.)
- **That trap is why `inspector` and `drafter` pin Sonnet**, and the gap is now measured:
  `reviewer`'s cell took 3.2x the time and 4.0x the cost of `inspector`'s on the review task,
  and `builder`'s 2.4x the time and 3.4x the cost of `drafter`'s on the implementation task,
  for the same score. Both tasks were saturated: that shows the pinned pair is enough for
  bounded work and nothing about escalation-shaped work, so the predicates did not move. The
  rung above `inspector` is not another tier: pass `effort: 'high'` on the call before you
  reach for a different tier. Change tier on an escalation predicate, not on a feeling.

## "Best model at lower effort" vs a multi-model cascade

The tempting shape is a cascade: haiku drafts, sonnet fixes, opus adjudicates. Measure the
single-model alternative — **the best model you can afford, at lower effort** — before
building one. The grid agrees on bounded work: `medium` matched `high` on Sonnet and Opus,
sooner.

- **A cheaper subagent model forfeits nothing from the orchestrator's cache.** A subagent
  never reads it: "Its first request doesn't read the parent's cache, because the two
  prefixes differ" (Claude Code docs, prompt-caching, read 2026-10-22). Only a fork inherits
  the parent's prefix, and a fork runs the parent's model. Each subagent writes its own
  prefix once and reads it on its later turns, at a 5-minute TTL by default even on a Claude
  subscription (`subagentPromptCacheTtl: "1h"` or frontmatter `experimental: { cacheTtl: 1h }`
  changes it; 1h writes bill 2x input against 1.25x for 5m).
- **What a cascade does cost in cache terms is sibling sharing.** Workflow siblings share a
  cached prefix only when they run with the same model, effort level, agent type, tools,
  output schema and working directory (Claude Code docs, workflows, read 2026-10-22); Claude
  Code holds matching siblings up to 5 s (`CLAUDE_CODE_WORKFLOW_PREFIX_STAGGER_MS`, default
  5000) so they read the first one's write. A uniform tier within a stage earns that sharing;
  mixing tiers inside one stage does not. Cross-stage cache reuse is not promised either way.
  Model-scoped cache loss is real in the main loop: `/model` switches, `opusplan` and a
  skill's `model:` frontmatter rebuild the orchestrator's cache.
- **Handoffs cost tokens twice.** Every stage boundary is a summary written by one agent and
  re-read as input by the next — overhead a single agent never pays.
- **Cascades multiply failure modes.** A weak first stage produces confidently wrong
  scaffolding later stages repair rather than replace.

Build a cascade when the stages are *genuinely different kinds of work* — a mechanical
extraction pass feeding one hard judgment call — not as a cost trick.

## Cost per completed task, not per request

Judge the tier on what it takes to reach an accepted result — in wall-clock as well as
dollars. Per-agent cost at the assumptions above is **$0.0065 haiku / $0.13 sonnet / $0.26
opus**. Ignoring the cost of noticing the failure, a Haiku run stops being cheaper than one
Sonnet run at **20 attempts** and than one Opus run at **40**; a Sonnet run stops being
cheaper than one Opus run at **2**. Those are on price; per task Haiku measured about 10x
cheaper than Sonnet, so the Haiku figures are upper bounds.

**The retry math, with noticing priced in.** Going cheap-first is cheaper only while the
first-pass failure rate `p` stays under

```
p* = (dear − cheap) / (dear + d)     in units of one Haiku run: Haiku 1, Sonnet 20, Opus 40

   d = your own cost to notice the failure and re-brief, in the same units. It is your
       reading cost, so it does not scale with the tier under test.
```

| cheap → dear | `d` = 0 | `d` = 3 | `d` = 20 |
|---|:--:|:--:|:--:|
| haiku → sonnet | 0.95 | **0.83** | 0.47 |
| haiku → opus | 0.97 | **0.91** | 0.65 |
| sonnet → opus | 0.50 | **0.47** | 0.33 |

`d` = 3 is an Opus 5.5 orchestrator reading a 2K-token failed report and writing a
500-token re-brief; `d` = 20 is noticing that costs a whole Sonnet run; `d` = 0 never
happens. In a long orchestration `d` also grows with the context every later request
re-reads (`orchestrator-cost.md`). A failed Haiku attempt is nearly free in dollars. What
it costs is the wall-clock of the failed attempt and the risk nobody notices. So the gate on
a Haiku tier is whether you can tell, quickly, that the result is wrong.

Symptoms that a cheap tier is silently costing more: repeated "close but wrong" returns on
one task shape; the caller rewriting the output instead of using it; turns burned re-reading
files; a `maxTurns` ceiling being hit. **What to do:** sample real tasks and count first-pass
acceptance. If failures exceed what the retry table tolerates — or, on a Haiku pair, their
wall-clock hurts first — promote and re-measure; otherwise hold and work on prompt and
context. Raise the *effort*, on the call, for thoroughness failures (right approach,
incomplete work); promote the *model* for capability failures (wrong approach, missed
implications).

## The 100K price cliff

Haiku 5.5 has a 1M window, so nothing here fails outright. Above 100K prompt tokens it bills
5x its base rate — Sonnet is then 4x its price, not 20x — and an agent's own tool output
counts toward the prompt. Mechanical does not mean small. Task shapes that cross the cliff
without looking like it:

- whole-file reads of any large file, or "read these N files and …"
- long logs, transcripts, diffs, or command output piped into context
- "survey the repo, then …" — the survey crosses the cliff before the *then*
- multi-file refactors, where every edited file is read, echoed back, and retained
- any open-ended loop over discovered items

`Explore` is the shape that stays small: it reads *excerpts*, not whole files, and skips
CLAUDE.md and the git-status snapshot. It runs on the main conversation's model, so in an
Opus session it is an Opus call at the session's effort — smallest prefix, not cheapest
model (see `agent-catalog.md` → "Explore"). Use it to locate code — it does not review or
audit it. Rule: if you cannot bound
what the agent will read, price the Haiku route at the long-prompt row. It is still the
cheapest row — a large input is `scout`'s shape — a cost to expect, not a reason to refuse.

## The tool surface is the biggest lever

Single paired run on this harness, 2026-09-30 — same model (`haiku` pinned on both, then
`claude-haiku-4-5`), same prompt, identical output. **Two things differ between the arms**,
tool count *and* `omitClaudeMd`, so the gap is their joint effect:

| agent | tools | cold-start prefix | total input, 9 requests |
|---|--:|--:|--:|
| `mechanical` (6 tools, `omitClaudeMd: true`) | 6 | 7.5k | **98k** |
| `general-purpose` (all tools) | all | 42.4k | **435k** |

**4.4× on one task** (n=1 per arm — treat it as the order of magnitude, not a constant). Two
ratios appear above and they measure different things: the cold-start *prefix* ratio is
42.4/7.5 = **5.65×**, while **4.4×** is total input over 9 requests, which dilutes the fixed
prefix with accumulated tool results. Tool schemas are re-sent every request, so the gap
compounds with turn count; CLAUDE.md is only ~500 tokens of it, by subtraction rather than by
a third arm.

Re-measured 2026-10-09 on Claude Code 2.1.295, on a one-line echo with no tool calls:
all-tools `general-purpose` billed **38,112** and **38,131** subagent tokens against
**6,824-8,869** for the scoped tiers — **4.3-5.6x** on the cold-start prefix alone. It is the
biggest *input* lever, paid on every request: more than the 2x on price between Sonnet and
Opus, less than the 20x on price between Haiku and Sonnet. Those levers multiply rather than
compete. Scope `tools:` before you touch model or effort.

## Two things that break the table above

**Haiku takes an effort setting.** `haiku` resolves to `claude-haiku-5-5`, which carries
`"effort"`, `"xhigh_effort"` and `"max_effort"` in the Claude Code 2.1.295 catalog and
honours an effort named on the call (probed 2026-10-09). What breaks the grid is leaving it
out. A subagent that names no effort runs at the **session's** effort, not at a default.
Every tier here pins one. `mechanical`, while it declared none, was observed on Haiku at
`xhigh` in an `xhigh` session, spending 90 thinking tokens on a one-line echo against 0 at
`low`. "Accepts no effort" stays true only of `claude-haiku-4-5`, whose capability list is
exactly `["context_management"]` and which no alias reaches.

**An advisor re-prices every row.** When a session has an advisor configured,
each subagent receives it — observed 2026-09-30 in one session as `claude-fable-5-1`, again
2026-10-09 in all nine probe transcripts, `mechanical` included, and on 2026-10-22 every
subagent assistant record carried `advisorModel: claude-opus-5-5`. The advisor *model* is
session configuration, not a harness constant: the catalog assigns each model an
`advisor_rank`, so another session resolves a different one. Besides `/advisor` and
`--advisor`, a persistent `advisorModel` setting exists (Claude Code docs, model-config, read
2026-10-22); both are allowlist-checked.

Billing (API advisor-tool doc, read 2026-10-22): a consult is billed at the **advisor
model's** rates for what the advisor reads and writes, reported separately in
`usage.iterations`; the executor's own tokens stay at the executor's rates. So price each
*consult* at the advisor's tier, not the whole fan-out. Typical advisor output is 1,400-1,800
tokens, 4,200-5,900 on hard tasks. The advisor must be at least as capable as the executor
(an Opus 5.5 executor can only take Opus 5.5, Opus 5, Fable 5.x or Mythos 5.x). The API
exposes `max_tokens` on the advisor tool (2048 cut advisor output about 7x with no detected
quality loss in Anthropic's n=40 test) and `max_uses` per request; Claude Code documents no
setting for either. Price at whatever your own session resolved. On price a single consult
from a Haiku agent costs more than the agent; a consult's real
cost and latency are unmeasured here, because none of the 240 sweep runs called it. The
controls are session-wide — `/advisor off`, or `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` for
scripted runs; a model reading this cannot issue either, so **ask the user**. Per-agent
suppression is not exposed through any documented surface: read in Claude Code 2.1.286 and
not re-read on 2.1.295, the advisor spec is pushed onto the wire `tools` array *after* the
client list and executes server-side, so it never reaches an agent's allow/deny filter.
`tools:` is the allowlist and is sufficient on its own for client tools; a `disallowedTools`
entry beside it is applied (Claude Code docs, sub-agents, read 2026-10-22) but redundant —
and it is still no route to suppressing the advisor. The attachment is gated on a resolved
advisor model plus internal `advisorActive`/`advisorDeferred` flags that no agent-definition
key reaches. Bundle internals rot fast — re-check on CLI upgrades.

## Reaching MCP tools from a tier, and reading the error when you cannot

MCP tools arrive **deferred**: the schema is not loaded and `ToolSearch` is the documented
loader. Since `tools:` is an allowlist that *replaces* the default set, a tier that does not
list `ToolSearch` cannot load any MCP tool. `worker`, `drafter`, `inspector`, `reviewer`,
`builder` and `judge` therefore list it. The two Haiku tiers, `mechanical` and `scout`,
deliberately do not: an MCP response is unbounded and shaped by a third party, and neither
"convert this by rule" nor "pull these named facts from this file" describes work against
one.

**Listing it is necessary, not sufficient — verified 2026-10-01.** A probe run as `reviewer`
tried to reach MCP and got:

```
Error: No such tool available: ToolSearch. ToolSearch is disabled for this
session, in subagents as well as here.
```

A session can disable `ToolSearch` outright, and the disable **propagates into subagents**.
When that is in force, no tier reaches MCP whatever its allowlist says, and the fix is at the
session/permission layer, not in a definition. The same probe found no `mcp__*` tool exposed
to the subagent at all, loaded or deferred. **The error text tells you which of three cases
you are in**, and the three have different fixes:

| what you see | what it means | where the fix is |
|---|---|---|
| bare `No such tool available: X`, no explanation | the name is not registered — wrong name, or that server is not configured for the session | the name, or the session's MCP config |
| `No such tool available: X. X is disabled for this session, in subagents as well as here.` | session-level disable, inherited by every subagent | session / permissions — ask the user |
| `No such tool available: X. X is not available in this session — <workaround>` | session-level unavailability with a suggested substitute | use the substitute, or ask the user |

A tool missing only from a definition's `tools:` list is a fourth case; our probe could not
isolate it, because the session-level disable masks it. Do not assume the same message.

**Corollary, and it bites: a `tools:` entry for a tool the session has disabled is inert.**
All eight tiers list `Grep` and `Glob`. In a session where both were disabled, a 92-agent
fan-out made **zero** `Grep` and **zero** `Glob` calls — the whole census was
`Bash 1524, Read 45, StructuredOutput 78, Write 1`, with every search done through `Bash`.
The declarations read as capabilities and were not. When a fan-out behaves as though a tool
does not exist, check whether it does before concluding the agents chose otherwise.

**`mcpServers` is a legal agent-frontmatter key**, and the declared channel for giving one
agent its own MCP servers. No tier here uses it, and whether it bypasses a session-level
`ToolSearch` disable is untested — the place to look, not a known workaround.

## How to set each knob

| Where | model | effort | maxTurns | omitClaudeMd | tools |
|---|---|---|---|---|---|
| `Agent` tool | ✅ `haiku`\|`sonnet`\|`opus`\|`fable` | ✅ `low`→`max`; overrides the definition's | ❌ | ❌ | ❌ |
| Workflow `agent(prompt, opts)` | ✅ same tiers; omit to inherit session | ✅ `low`→`max`; omit to inherit session | ❌ | ❌ | ❌ |
| Agent definition frontmatter | ✅ alias, full id, or `inherit` | ✅ `low`→`max`, or an integer; honoured at runtime | ✅ | ✅ | ✅ **biggest lever** |
| `SKILL.md` frontmatter | ❌ | ⚠️ sets *this turn*, never a subagent (see below) | ❌ | ❌ | `allowed-tools` |

Call-site `effort` beats the definition's, which beats the session's (and
`CLAUDE_CODE_EFFORT_LEVEL`, when set, beats all three); nothing falls back to
the catalog default. Probed 2026-10-09: a definition's `high` held in an `xhigh` session, a
call-site `low` overrode a definition's `high`, and a call naming no effort ran at the
session's `xhigh`. The `Agent` tool's own rule is to set `effort` only when a user or a skill
asks; this skill asks. To raise one call's effort without changing tier:
`Agent({ subagent_type: "intelligent-delegate:inspector", effort: "high", ... })`, or
`agentType` plus `effort` in a Workflow `agent()`. `max` was neither probed nor measured. The
`Agent` tool's per-call `effort` needs Claude Code v2.1.292 or later.

**Model resolution order** (Claude Code docs, sub-agents and model-config, read 2026-10-22):

1. the call's `model` parameter;
2. the definition's `model` (`inherit` means the main conversation's model);
3. `CLAUDE_CODE_SUBAGENT_MODEL`;
4. the main conversation's model.

Since v2.1.251 the env var no longer beats `model: inherit`. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`
(v2.1.257+) makes the env var override every definition's `model`, every workflow `model`
option and the call's `model`, so all tiers collapse onto one model. On effort,
`CLAUDE_CODE_EFFORT_LEVEL` beats both frontmatter `effort` and the call's `effort`, and
`maxEffortLevel` caps it. A family alias passed on the call (`model: "opus"` from an Opus
session) resolves to the parent's exact model. A mid-session `/model` switch also moves what
the `inherit` tiers run on. Subagents inherit the session's extended-thinking on/off
(v2.1.198+); there is no per-subagent thinking setting.

```markdown
<!-- agents/worker.md, as shipped — what one name carries -->
---
name: worker
model: sonnet
effort: medium
maxTurns: 25
---
```

`Agent({ subagent_type: "intelligent-delegate:worker", ... })` gets the model, the effort,
the turn cap, the tool allowlist and the operating rules from one name. A bare `Agent` call
can name a model and an effort too; what only a definition sets is `tools`, `maxTurns` and
`omitClaudeMd` — and a pin that holds whether or not the caller remembers it. Plugin agents
are namespaced; bare `mechanical` resolves only for a project-local
`.claude/agents/mechanical.md`.

`SKILL.md` frontmatter: `effort:` there **is** honoured by this harness — the release notes
record fixing it being ignored on some models. But it sets **the invoking turn's** effort,
never a subagent's, so it is not a delegation lever. It is also **not in the published Agent
Skills spec** — which allows only `name`, `description`, `license`, `allowed-tools`,
`metadata`, and `compatibility` — so the official `skill-creator` validator rejects it and
the skill stops being portable. That is why this plugin puts its tiering in `agents/*.md`,
where `effort:` is both documented and spec-legal.

## Platform features checked 2026-10-22, and whether they reach Claude Code

Read against the API and Claude Code docs on 2026-10-22. Re-read before relying on a row;
several are betas or research previews.

| Feature | What the docs say | Reachable from Claude Code? |
|---|---|---|
| Fast mode | Opus 5.5 (GA); Opus 5 and 4.8 (research preview); not Sonnet, Haiku or Fable. Up to 2.5x output tokens/s, no time-to-first-token gain, same model quality. Opus 5.5 fast is $8/$40 per MTok (2x). On the API, requests at different speeds don't share cache. Not available with Batch | `/fast` for the session. In Claude Code the first fast turn of a conversation rebuilds the cache once; after that, toggling fast mode on or off keeps it (Claude Code docs, prompt-caching). Whether subagents get it is not documented, and no tier here runs Opus except `judge` and the inherit tiers in an Opus session. Unmeasured here |
| Task budgets | Beta `task-budgets-2026-03-13`, `output_config.task_budget`: a soft advisory token budget for a whole agentic loop, minimum 20K; `max_tokens` stays the only hard cap | "Not supported on Claude Code or Cowork". `maxTurns` remains the only per-agent bound |
| Batch processing | 50% off; most batches finish within 1 hour; 24h expiry | API only: no Claude Code subagent route. Relevant only to offline evals that call the Messages API directly |
| Per-message (mid-conversation) effort | API beta `mid-conversation-output-config-2026-07-01` keeps the cache | In Claude Code, changing effort with `/effort` keeps the cache on Opus 5.5, Sonnet 5.5, Haiku 5.5 and Fable 5.1 with an API key or subscription; not on Bedrock, Google Cloud Agent Platform, a Claude apps gateway, HIPAA, or with `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`. Fast-mode speed switches do miss the cache |
| Compaction / context editing | API features | Native-1M models auto-compact only near ~967K tokens; `/autocompact 200k` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW` lowers it; `/compact <focus>`; per-subagent `autoCompactWindow` frontmatter (100000-1000000, v2.1.296+). After compaction each invoked skill body is re-injected capped at 5,000 tokens (25,000 total, oldest dropped first), so keep a skill's essentials at its top |
| Thinking | Adaptive thinking is on by default on the 5.x models and cannot be disabled on the 5.5 models or Fable. Thinking tokens bill as output whether or not they are displayed. Effort is the documented first lever on thinking cost | Subagents inherit the session's thinking on/off; no per-subagent setting |
| `max` effort | Claude Code docs: "may show diminishing returns and is prone to overthinking, so test before adopting it broadly" | Session-only unless set by env var. Not measured here |
| Opus 5.5 at `medium` | "Matches or exceeds Opus 5 at `high` on coding and knowledge-work evaluations" (Claude Code docs, model-config); Opus 5.5 defaults to `medium` | Yes: it is the default in Claude Code |
| Tool search / programmatic tool calling | Tool search defers tool definitions (>85% definition-token savings on a 5-server MCP setup, per the API doc). Programmatic tool calling is API-only | Claude Code uses tool search for MCP tools (see "Reaching MCP tools from a tier"). Programmatic tool calling: no |
