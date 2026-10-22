---
name: delegate
description: "Routes work to the right execution shape — inline, one subagent, or a Workflow fan-out — and picks the model tier and reasoning effort for each, for speed, result quality and cost together, including what the orchestrator's own context costs. Use whenever delegation, parallelism, subagents, background agents, or agent cost or speed comes up: \"should I delegate this or do it inline\", \"which model for these agents\", \"what effort level\", \"fan this out\", \"run these in parallel\", \"spawn some agents\", \"this is burning too many tokens\", \"why was this session so expensive\", \"can something cheaper do it\", \"these agents are too slow\", \"Workflow or one Agent call\", or when a delegated result came back wrong. Read it before writing any Workflow script: an agent() call with no agentType inherits the session's model and effort, and reviewer/builder are model: inherit, so three measured fan-outs ran entirely on Opus."
license: MIT
---

# Delegate

Routing guidance for handing work to subagents, for **speed, result quality and cost,
together** — the orchestrator's own spend included. Read the ladder, stop at the first
match, and read further only if that call was close. The measurements and platform facts
behind each rule live in `references/`; this file keeps the rules, most important first.

## If you are writing a Workflow script, read this first

**Every `agent()` call needs an `agentType`.** Three measured fan-outs ran 100% on Opus
(2026-09-30 twice, 2026-10-08), one of them in a session that had this skill loaded. Two
distinct causes, and you need both fixes:

1. **Omitting `agentType` is not a cheap tier — it is no tier.** The call inherits the
   session's model **and** its effort, and loses the definition's `maxTurns`, tool
   allowlist, `omitClaudeMd`, operating rules and return-value contract. In an Opus
   session at `xhigh` that measured 6.2x the time and 6.6x the cost of `sonnet/medium` for
   the same score. The Workflow tool's own canonical example omits `agentType` on its
   build stage, and that example is what gets copied.
2. **`reviewer` and `builder` are `model: inherit`.** They pin `high` effort on the
   *session's* model; in an Opus session they are Opus. They are escalations; `inspector`
   and `drafter` are the defaults.

**Default tier by stage kind.** Start here and depart with a reason:

| the stage | tier | what it is |
|---|---|---|
| generate / draft prose or code | `intelligent-delegate:drafter` | sonnet, high, writes |
| review / verify / audit | `intelligent-delegate:inspector` | sonnet, medium, read-only |
| fully-specified fix from findings | `intelligent-delegate:worker` | sonnet, medium, writes |
| transcribe prose into a schema | `intelligent-delegate:mechanical` | haiku, low, writes (or delete the stage — put the `schema` on the upstream agent) |
| the one call that gates the result | `intelligent-delegate:reviewer` | session model, high |
| contested tie-break, after a split | `intelligent-delegate:judge` | opus, xhigh |
| *not a default:* pull named facts from a large input, where you can check the answer | `intelligent-delegate:scout` | haiku, low, read-only |

**One stage needs more than its tier gives? Raise effort on the call before changing
tier:** `agent(prompt, {agentType: 'intelligent-delegate:inspector', effort: 'high'})`.
**Generation and verification are different jobs and must not share a tier** — a
workflow that runs every stage at the session tier is anti-pattern 14.

A `PreToolUse` hook ships with this plugin. It **blocks** a `Workflow` whose `agent()`
calls have no `agentType`; it **notes** an `Agent` call that names no tier and no model;
and it warns once per session when an environment variable overrides every tier (see
"Settings that silently override the tiers"). If no shipped definition fits a workflow
stage, put `// untiered: <reason>` on or just above the call and name an `effort` on it.
The hook fails open on anything it cannot parse: a backstop, not a gate to lean on.

## Route it in ten seconds

Answer the first question that hits. Stop there. Everything below is backing detail.

1. **Is this ONE target, and would the subagent keep most of what it reads?** →
   **do it inline.** It is a *volume* test, not a turn-count test ("digest this 60K-line
   changelog" is two tool calls and still belongs in a subagent), and a *single-target*
   test, not a "do I know the filenames" test ("apply this same edit to 12 board
   directories" names every file up front and is still a fan-out).
2. **Did you already spawn an agent that holds this context — running or finished?** →
   **`SendMessage` it.** A finished subagent resumes with its full history; its prompt
   cache stays warm for 5 minutes by default. `Explore` and `Plan` are one-shot and cannot
   be resumed.
3. **Name the payoff you are buying** — context protection, tier arbitrage, or
   wall-clock parallelism. Can't name one? → **inline.** (Payoffs are not exclusive, and
   naming one does not commit you to a cheap tier.)
4. **One target, bounded question, big search, small answer?** → **one Agent call, with a
   tier named:** `inspector` for a read you will act on, `scout` when you can check the
   answer and cost matters. Do not omit `model` to "inherit" — that is the session's
   model at the session's effort with every tool schema in the prefix. When an escalation
   predicate fires, `reviewer` (read-only) or `builder` (writes) inherit reliably and pin
   `high`.
5. **Three or more similar items, or more than one stage per item?** → **Workflow,
   `pipeline()`.** This beats rule 1 whenever they disagree — item count wins over "I know
   which files". It also costs the orchestrator one result instead of one wake-up per
   agent (next section).
6. **Need a validated `schema`?** → **Workflow**, even for a single item. **This rule
   outranks 1 and 3**, the same way 5 does: a `schema` is a correctness mechanism, not a
   payoff. A specific effort level is *not* a reason — the `Agent` tool takes `effort`.
7. **Still unsure?** → inline. The floor is higher than it feels.

**Precedence, when two rules fire:** 5 and 6 beat 1 and 3. Within those, answer in order.

**Losing tier arbitrage does not un-justify the delegation.** If a gate later disqualifies
the tier you had in mind, step up **one rung** and collect the other payoffs instead:
failing the Haiku gate lands you on `drafter`/`inspector` (pinned Sonnet), not on the
session model; only an *escalation* predicate takes you to `builder`/`reviewer`. The
ladder decides shape; the predicates decide tier.

## The orchestrator is a cost centre

**Measured 2026-10-22**, a real 50-minute build in an Opus 5.5 session at `xhigh`, every
subagent correctly tiered on `drafter`. Claude Code's own accounting: the **orchestrator
was $16.47 of $21.77 — 76%** — from 44.6M cache-read tokens over a ~395K-token context.
The Sonnet agents that did the building cost $5.29. Tiering the agents was right, and it
was the smaller term.

Why it happens:

- **Every orchestrator request re-reads the whole context** at the session model's
  cache-read rate: on Opus 5.5 ($0.20/MTok), ~$0.08 per request at 395K, before any output.
- **Each background completion is a new orchestrator turn.** Subagents spawned from the
  main conversation start in the background by default, and each result arrives as a
  completion notification in a later turn — at least one more full re-read per agent.
- **A cheap subagent does not make the orchestrator cheaper.** Subagents never read the
  orchestrator's cache, and what they report back grows the context every later request
  re-reads.

The levers, in the order they pay:

1. **Fan out through a Workflow, not N background `Agent` calls.** The script holds the
   loop and intermediate results, so the orchestrator receives only the final answer. If
   you do use `Agent` calls, ask for short reports (a verdict and paths, not a narrative),
   and make a call foreground (`run_in_background: false`) when you would only wait for it
   anyway: it returns inline, with no separate wake-up turn.
2. **Keep bytes out of your own context.** Have agents write long output to files and
   return paths; grep files instead of reading them whole; never read an agent's
   `.output` transcript; delegate any large read you do not need verbatim (high `D`).
3. **Compact at phase boundaries, while the cache is warm.** Native-1M models do not
   auto-compact until about 967K tokens. Between waves, suggest `/compact <focus>` to the
   user — or `/clear` and re-brief from a state file you wrote — and `/autocompact 200k`
   for a long orchestration. Only the user can issue these; say so at a natural break.
4. **Mind the orchestrator's effort.** Opus 5.5 defaults to `medium`, which Anthropic
   reports matches or exceeds Opus 5 at `high`; `xhigh` is a deliberate choice. On the 5.5
   models and Fable 5.1, `/effort` changes keep the cache, while a `/model` switch
   rebuilds it — for a long dispatch-and-wait phase, suggest `/effort medium`.
5. **Mind the cache lifetime.** API-key sessions get a 5-minute main-loop cache. If agent
   completions arrive more than 5 minutes apart, each wake-up rewrites the context at
   1.25x input instead of reading it at 0.05x — 25x more on Opus 5.5. The
   `promptCacheTtl: "1h"` setting fixes that (1h writes bill 2x). Subscription sessions
   already get 1h on the main loop; subagents and workflow agents get 5 minutes unless
   `subagentPromptCacheTtl` says otherwise.
6. **Measure it.** `python3 <plugin root>/scripts/delegation_audit.py [session-id]` (or
   `/intelligent-delegate:audit`) splits a session's spend into orchestrator and each
   subagent and flags these patterns. Details: `references/orchestrator-cost.md`.

## The delegation floor

Every subagent starts cold: fresh system prompt, tool definitions, `CLAUDE.md` and a git
status snapshot, no conversation history. Its final report is **not shown to the user** —
you read it and relay it. So delegation never reduces total tokens; it relocates them and
adds some. It saves you only the tokens the subagent **discards**:

```
savings = D − (S + C + B + 2R)

D  tokens the subagent reads and throws away (never need to reach you)
S  its system prompt + tool definitions — NOT fixed: the `tools:` list controls it
C  CLAUDE.md, re-injected per subagent  — wc -c ~/.claude/CLAUDE.md ./CLAUDE.md, ÷4 ≈ tokens
B  the brief: every fact from this conversation you must restate, because it cannot see it
R  the report — counted TWICE (its output, then your input), and then re-read by every
   later orchestrator request until you compact
```

**`S` is the term you can actually move, and it tracks tool count — not model tier.**
Budget `S + C` at **about 7-9k** for a scoped definition and **about 38k** for an
all-tools agent (measured 2026-10-09: 6,824-8,869 subagent tokens for the scoped tiers
against 38,112 for `general-purpose`). **If D is not clearly larger than that cold start,
do it inline.**

- **High D** — grepping a large tree for one fact, reading a long build log, scanning
  forty files to find the three that matter, driving a browser. Delegate these.
- **Low D** — anything whose output length approaches its input length: translating a
  paragraph, renaming a symbol, one function from a spec you would have to write out anyway.
- **Long-form prose for the user is a bad delegation target.** You pay `R` twice, then
  reproduce it. Unless D is genuinely large, write it yourself.
- **Cut `S` first, then `C`.** A narrow `tools:` list is worth far more than
  `omitClaudeMd: true` (which `mechanical` and `scout` set, and which still loads the git
  status snapshot). Never set it when the task depends on project conventions.
- **Specify the report's shape and length in the brief.** After D, `R` is the only term
  you control, and in a long orchestration it is re-read on every later request.

You delegate to buy at least one of three things. Name one before you call:

| Payoff | What you are buying | Test that decides it |
|---|---|---|
| Context protection | The conclusion without the bytes — which also keeps every later orchestrator request cheaper | Will you edit against these files? No → delegate |
| Tier arbitrage | Bulk work at Haiku's or Sonnet's rate instead of the session's — 1x or 20x on price where Opus is 40x | 3+ near-identical items with an objective done-condition |
| Wall-clock parallelism | Independent branches while the user waits | No item reads another item's output |

## The two boundaries

**Inline → one Agent.** The discriminator is *context asymmetry*: the search is large,
the answer is small. A grep that may touch forty files and returns one path is
delegation. A grep that returns the bytes you are about to edit is not.

**One Agent → Workflow.** Any one of these flips it:

- Three or more similar items. Up to 16 agents run concurrently by default, fewer with
  fewer CPUs (`CLAUDE_CODE_WORKFLOW_MAX_CONCURRENT_AGENTS`, 1-256); 1,000 per run.
- More than one stage per item.
- You need a validated `schema`. This flips even a single item.

**All eight tiers work inside a Workflow.** `agent(prompt, {agentType:
'intelligent-delegate:drafter'})` gets that definition's model and effort, and `effort`
beside it adjusts that one call. Use `{model, effort}` with no `agentType` only when no
shipped definition fits; name both, and mark the call `// untiered: <reason>`. Such an
agent gets none of a definition's limits or rules: `{effort: 'high'}` is not `reviewer`.

Inside a Workflow, `pipeline()` is the default — per-item streaming, no barrier. Reach
for `parallel()` only when stage N needs cross-item context from **all** of stage N−1
(dedup, rank, early-exit on zero). **Siblings share a cached prefix** only when they run
with the same model, effort, agent type, tools, schema and working directory — a uniform
tier per stage earns it; a per-item `effort` override takes that item out of it.

**Isolation.** Isolate when an agent's inputs can change while it runs: two or more agents
write the **same paths**; any agent runs **git operations**; or **you will keep editing
files the agent is reading**. Disjoint writes need no worktree. A worktree branches from
your **default branch, not your HEAD**, so a reader in one does not see uncommitted or
unmerged work.

**Coordinating with agents you have already spawned.** A subagent reading a file you are
rewriting re-reads, notices the mismatch, and burns turns re-verifying (measured: one
`reviewer` spent 26 Bash calls establishing which version it was looking at). In order of
preference: (1) **freeze, then brief** — commit and name the SHA ("review SKILL.md at
`abc1234`"; the agent can `git show <sha>:<path>`), then leave those files alone;
(2) **batch your edits** until the read-only stage returns; (3) a worktree, with the
base-branch caveat above. Say in the brief which files are frozen and which are moving.

Script hygiene, because a dead script costs the whole run: `Date.now()`,
`Math.random()` and argless `new Date()` **throw** (pass a timestamp in `args`).
`agent()` returns `null` on skip or death — `.filter(Boolean)`.

## Effort, and how to actually reach it

**A subagent that names no effort runs at the *session's* effort, not at a default.**
Every tier here pins one. Precedence, highest first: the `CLAUDE_CODE_EFFORT_LEVEL`
environment variable (beats everything below — see the overrides section), the call's
`effort`, the definition's frontmatter `effort:`, the session's. Probed on Claude Code
2.1.295: a Haiku definition with no `effort:` ran at `xhigh` in an `xhigh` session; a tier
declaring `high`, called with `effort: 'low'`, ran at `low`.

The two places you control:

1. **The definition.** Frontmatter `effort:`, reached by naming the definition as
   `subagent_type`, or as `agentType` in a Workflow.
2. **The call.** The `Agent` tool takes `effort` (`low|medium|high|xhigh|max`, v2.1.292+)
   and it overrides the definition's; in a Workflow, `agent(prompt, {agentType, effort})`.
   The tool's rule is that effort is set only when the user or a skill asks. **This skill
   asks:** pass `effort` on any call that does not go through a pinned tier, and raise or
   lower a tier's effort at the call site instead of changing tier.

**Prompt wording does not set effort.** "Think hard" in a brief is ordinary text: at most
it nudges thinking, unreliably on Sonnet 5.5 and Haiku 5.5. `ultrathink` in a turn you
write adds an in-context instruction, and the API effort is unchanged. A skill's
frontmatter `effort:` sets the **invoking turn's** effort — a lever for the orchestrator's
own turn, never a subagent's. `max` is documented as "prone to overthinking"; it is
unmeasured here.

**Pin `medium` for bounded work.** `low` saved 8-17% and is where every Sonnet and Opus
miss happened; `high` took 1.4-1.9x as long and `xhigh` 2.9-3.9x, and neither improved a
score (saturated tasks: `medium` is enough for that difficulty, nothing more is shown).
Claude Code's own defaults are `medium` on Opus 5.5, Sonnet 5.5 and Haiku 5.5 and `high`
on Fable 5.1 — but a subagent gets the *session's* unless pinned. Sonnet 5.5 at `xhigh`
starts its own review rounds, sometimes with subagents, per Anthropic's guide: one more
reason not to let a tier inherit `xhigh`.

**Lower effort before lowering model.** Within one model the judgment you rely on stays
put, and in the main loop an effort change keeps the cache on the 5.5 models where a
`/model` switch rebuilds it. For a subagent, cache is not the argument — it never reads
the orchestrator's — but effort was still the larger speed lever measured.

**A bare `Agent` call reaches any model at any effort**, since `model` and `effort` are
both on it — but only a definition sets `tools`, `maxTurns`, `omitClaudeMd`, the operating
rules and the return contract, so name the nearest tier and adjust its effort on the call.
**Mapping a cell to a tier.** haiku/low is `mechanical` (writes) or `scout` (read-only);
sonnet/medium is `worker` or `inspector`; sonnet/high is `drafter`, or `inspector` with
`effort: 'high'`; opus/xhigh is `judge`; the session model is `builder` (writes) or
`reviewer`, both pinned at `high`. The Agent tool's `model` enum is
`haiku|sonnet|opus|fable` with no `inherit` value; the reliable inherit route is a
definition that says `model: inherit`.

## Speed

Measured 2026-10-09 (`evals/tier-sweep/RESULTS.md`): 240 runs, four bounded tasks, from a
`claude-opus-5-5` session at `xhigh`. Mean of the four per-task means:

| cell | what runs there | seconds | cost $ | score |
|---|---|--:|--:|--:|
| `haiku/low` | `mechanical`, `scout` | 18.3 | 0.0041 | 0.988 |
| `sonnet/medium` | `worker`, `inspector` | 14.0 | 0.0441 | 1.000 |
| `sonnet/high` | `drafter` | 21.6 | 0.0586 | 1.000 |
| `opus/high` | `reviewer` and `builder`, in an Opus session | 41.7 | 0.1672 | 1.000 |
| `opus/xhigh` | an untiered call from that session; the cell `judge` pins | 86.2 | 0.2923 | 1.000 |

Levers, in the order they paid: **effort** (largest — against the same model at `medium`,
`xhigh` took 2.9x the time on Haiku, 3.7x on Sonnet, 3.9x on Opus), then **tier** (Sonnet is the fast model; Haiku is the cheap
one — at `medium` it took 1.6x Sonnet's time, writing about three times the output), then
**shape** (judged: a fan-out hides per-agent latency, and `pipeline()` has no barrier).
This is strong evidence on time and cost and weak evidence on quality: it loosens no
escalation predicate.

**Fast mode** (`/fast`) runs Opus 5.5 at up to 2.5x output tokens per second for 2x the
price, with no time-to-first-token gain; it is Opus-only, and the first fast turn of a
conversation rebuilds the cache once. Where the orchestrator's cost is context re-reads, it doubles the dominant term:
use it for output-heavy turns a person is waiting on, not for a dispatch-and-wait phase.
Unmeasured here, as are `max` effort and an advisor consult.

## Model tier: the two gates and their predicates

The price ladder: **Haiku 1x / Sonnet 20x / Opus 40x / Fable 100x, input and output
alike** — about 10x measured between Haiku and Sonnet, since Haiku writes about three
times the output. Haiku 5.5 bills every rate 5x on a request whose prompt exceeds 100K
tokens. Cache reads are 0.10x input on Haiku 5.5, **0.05x on Sonnet 5.5 and Opus 5.5**, and
0.025x on Fable 5.1. Full table: `references/model-selection.md`.

**The default depends on how many agents you are about to spawn.** One agent that needs
session-model judgment → inherit (`reviewer` / `builder`), unless the job is plainly
ordinary. **A fan-out, or any multi-stage Workflow → start at the pinned-Sonnet rung**
(`drafter` to generate, `inspector` to verify) and escalate only the stages where an
escalation predicate fires.

There are **two** tier decisions and they do not share a test:

| Gate | The question | The list to use |
|---|---|---|
| **Escalation gate** | pinned Sonnet → the session model? | the *escalation* predicates, next. Narrow: pinned Sonnet is already a judgment-capable tier, and `effort: 'high'` on the call is the step before it |
| **Haiku gate** | Sonnet → `mechanical` or `scout`? | detectability, then the no-downgrade predicates. Strict: what a miss costs is not the retry, it is not noticing |

**The verb is not an escalation trigger.** "Review, audit, assess" is a reason not to send
work to **Haiku**; it is not a reason to escalate, because `inspector` exists to review.

**Escalation — pinned Sonnet to the session model. Any ONE is enough:**

- **Two readings of the brief survive a careful read.** If you cannot tell, that is the
  second reading surviving. ("Apply the same edit to each": an identical literal diff, or
  the same *kind* of change adapted per target?) **Kill one first if you can** — ask, or
  read one target; across a fan-out that beats escalating every item, and you tier by the
  answer: a literal diff to `mechanical` or `worker`, a per-target adaptation to `drafter`.
- **Correctness rests on an invariant not written in the brief** — a codebase convention,
  a lock ordering, a schema constraint the agent would have to infer.
- **The deliverable contains a negative or universal claim** — "no other callers",
  "nothing else writes this field". Absence proofs need exhaustive reading.
- **Blast radius is security, auth, money, deletion, migrations or concurrency.**
- **Failure would be silent to you**, or you will build many turns on the result without
  re-checking it. Escalate on blast radius, not on difficulty.

Nothing else earns it — not "this one matters", not the verb, not a long input (Sonnet and
Opus each got 200 of 200 answers on the extraction task). One more shape does: **one
cross-cutting pass over every item at once** — one agent, not one per item.

**The Haiku gate is detectability.** A failed Haiku attempt is nearly free in dollars —
retried on Sonnet it is 21 units against 20 — so the gate is whether you can tell,
quickly, that the result is wrong. **No-downgrade, any ONE disqualifies:** any escalation
predicate; a verb of *review, audit, assess, decide, is-this-safe, did-I-miss* (no
deterministic check — its home is `inspector`); a failure that would be silent.
**Safe-downgrade, ALL must hold:** the work is specified by rule or example (`mechanical`)
or is extraction of named facts (`scout`); items are homogeneous; output is validated by
something deterministic you **will actually run**, or by quoted evidence you will read; a
failure is detectable at a glance. The retry break-even table is in
`references/model-selection.md` → "Cost per completed task".

**Route the check with the task**, in this order: (1) **deterministic** — a `schema`, a
test, a build, a grep; a `schema` on every stage that feeds another is free validation at
the seam; (2) **caller reads it** — only when the report is small; (3) **adversarial
pass** — hand `inspector`, or `reviewer` on a predicate, the artifact *and* the brief and
ask it to find what is wrong. "Confirm this is correct" gets agreement; "find what is
wrong" gets review — and a reviewer asked for gaps usually reports some, so scope it to
correctness against stated requirements.

## Settings that silently override the tiers

Each of these changes what every tier runs, and nothing in a definition can stop it. The
shipped hook reports the first two once per session; check the rest when a tier's cost or
behaviour looks wrong.

- **`CLAUDE_CODE_EFFORT_LEVEL`** beats both a definition's `effort:` and the call's
  `effort`: every tier runs at that level.
- **`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`** with `CLAUDE_CODE_SUBAGENT_MODEL` set makes
  every subagent and workflow agent run that one model, ignoring definitions and the
  call's `model`. Without `_FORCE`, `CLAUDE_CODE_SUBAGENT_MODEL` is only a default for
  agents with no model of their own; since v2.1.251 it no longer beats `model: inherit`.
- **A mid-session `/model` switch** moves the `inherit` tiers with it.
- **Thinking on/off** is inherited from the session; there is no per-subagent setting.
- **A fallback model chain** can switch a subagent's model mid-run (it reports
  `⚠ This agent switched to <model>`): a silent tier change worth watching in reports.
- **The advisor.** A session's advisor (`/advisor`, `--advisor`, or the `advisorModel`
  setting) is attached to **every** subagent, appended server-side after the client tool
  list, so no per-agent setting removes it. Observed: Fable 5.1 (2026-09-30, 10-09) and
  Opus 5.5 (2026-10-22). A consult bills at the advisor's rates for what it reads and
  writes; the agent's own tokens stay at its tier — so **price each consult at the
  advisor's tier**, and expect a `mechanical` fan-out to cost more than its tier says if
  agents consult. The controls are session-wide: `/advisor off`, or
  `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` for scripted runs. Only the user can issue
  `/advisor off`; for a large cheap fan-out where cost predictability matters, ask.
  On `judge` or `reviewer`, a stronger second opinion is the point; on bulk clerical work
  it is cost inversion.

## Fable

**Never set `model: "fable"` on a subagent.** Fable is the top of the ladder (100x Haiku,
2.5x Opus), a subagent's output is intermediate — you read it, compress it, relay it —
and if your session is not Fable you are paying a premium for an improvement you are
structurally unable to verify. If your session is Fable, inheriting already gives you
Fable. Anthropic's guide reports Fable 5.1 at `low` as often cost-competitive per task;
that is unmeasured here and does not answer the verification argument. If the subagent's
raw output *is* the whole deliverable, do it in the main loop where you can iterate.

## Agent type

Shipped definitions are namespaced (`intelligent-delegate:mechanical`, …) — eight tiers.
Full per-tier detail: `references/agent-catalog.md`.

| type | route here for | never route here for |
|---|---|---|
| `Explore` | locating — which files, where defined. Smallest cold-start prefix (no CLAUDE.md, no git status) **but on the session model**; one-shot, not resumable | review, audit, absence proofs — it reads excerpts. A large locate whose answer you can check is cheaper on `scout` |
| `Plan` | step-by-step plans, critical-file lists; inherits the session model; one-shot | execution |
| `general-purpose` | open-ended multi-step needing every tool | anything a tier covers — it carries every tool schema (about 38K of prefix) |
| `mechanical` (haiku/low, writes) | homogeneous work specified by rule or example — renames, format and lint fixes, record conversion — in a fan-out where parallelism hides its latency; it already pins `low` | judgment; one latency-sensitive call (`worker` is faster); MCP work (no `ToolSearch`) |
| `scout` (haiku/low, read-only) | pulling named facts from a large input **you can check** | review, audit, absence proofs, any verdict; one read you will act on unchecked; MCP |
| `worker` (sonnet/medium, writes) | well-specified implementation with a deterministic check; the fastest cell with no misses | ambiguous specs — it picks a reading and commits |
| **`drafter`** (sonnet/high, writes) | **the default generation tier**: docs from an evidence file, a runbook, a scoped implementation | genuine ambiguity or silent-failure blast radius (`builder`); fully specified output (`worker`, 41% faster) |
| **`inspector`** (sonnet/medium, read-only) | **the default inspection tier**: review, verification, audit, a read you will act on | absence proofs, security/auth/money blast radius, a verdict carrying many turns (`reviewer`) |
| `reviewer` (inherit/high, read-only) | the escalation above `inspector` | ordinary review (3.2x the time, 4x the cost of `inspector` in an Opus session); producing the fix |
| `builder` (inherit/high, writes) | the escalation above `drafter` | fully specified or ordinary generation (2.4x the time, 3.4x the cost of `drafter`) |
| `judge` (opus/xhigh) | the call you cannot afford to get wrong; breaking a tie between verdicts | routine work (6.2x the time, 6.6x the cost of `worker` for the same score) |

**MCP work.** MCP tools arrive deferred and `ToolSearch` loads them, so a tier must list
`ToolSearch` to reach one — every tier except `mechanical` and `scout` does. A session can
disable `ToolSearch` outright, and subagents inherit that. Read the error before
concluding a tier "cannot do MCP": `references/model-selection.md` → "Reaching MCP tools".

## Anti-patterns

1. **Delegating context you already loaded.** D = 0. You pay `S + C + B + 2R` for nothing.
2. **A fresh Agent call to ask a follow-up.** `SendMessage` the agent — finished ones too.
3. **Asking for effort in the prompt text.** Pass `effort` on the call, or name the tier.
4. **Routing to a Haiku tier for speed, or for a read you will not check.** Haiku is the
   cheap model, not the fast one.
5. **Using `Explore` to answer a correctness question** — or to save money in an Opus
   session. It locates, on the session model.
6. **`parallel()` where `pipeline()` works.** Every item now waits for the slowest.
7. **Skipping verification on work you will ship.**
8. **Building a multi-model cascade before measuring the best model at lower effort.**
9. **Not relaying the report.** The user never sees it.
10. **Spawning an all-tools agent for a narrow job.** About 38k of prefix against 7-9k.
11. **Editing files an agent you spawned is reading.** Commit first and pin the SHA.
12. **Assuming the tier price is the total.** An advisor can be consulted from any tier.
13. **Silent caps.** If you bound coverage — top-N, no-retry, sampling — say what was dropped.
14. **A uniformly-tiered fan-out.** Generation prices on clerical work and clerical prices
    on the call that decides whether the output is right. Tier per stage.
15. **Reading `model: inherit` as "the cheap option".** In an Opus session it is Opus.
16. **Leaving effort unset.** The agent runs at the session's effort, not at a default:
    Haiku at an inherited `xhigh` measured 2.5x slower than at `low`, for the same score.
17. **Raising effort on bounded work.** Raise it for a reason you can name, on one call.
18. **An orchestrator that reads everything.** Every byte you load is re-read by every
    later request at the session model's rate. Delegate big reads; keep reports short.
19. **N background `Agent` calls for one fan-out.** N wake-ups, each re-reading your
    context. A Workflow returns one result.
20. **Switching `/model` mid-orchestration to save money.** It rebuilds the cache; on the
    5.5 models `/effort` does not.

## References

- `references/orchestrator-cost.md` — the 2026-10-22 measurement, wake-up and rebuild
  arithmetic per model and context size, and how to run `scripts/delegation_audit.py`.
- `references/model-selection.md` — prices and cache rates, the measured grid, retry
  break-evens, the 100K cliff, platform features checked 2026-10-22, how to set each knob.
- `references/workflow-patterns.md` — barrier decision, named fan-out shapes, per-stage
  tiering, what a fan-out costs the orchestrator.
- `references/agent-catalog.md` — every `subagent_type` with its model, effort, tool
  surface, model-resolution order, and use/don't-use lines.
