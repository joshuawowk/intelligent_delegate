---
name: delegate
description: "Route work to the right execution shape and tier — inline, one subagent, or a Workflow fan-out — and which model and reasoning effort each one gets, for speed, result quality and cost together. Use whenever delegation, parallelism, subagents, or agent cost or speed comes up, including short asks like \"should I delegate this or do it inline\", \"which model for these agents\", \"what effort level\", \"fan this out\", \"run these in parallel\", \"spawn some agents\", \"this is burning too many tokens\", \"can something cheaper do it\", \"these agents are too slow\", \"make this fan-out faster\", \"Workflow or one Agent call\", \"is the overhead worth it\", or when a delegated result came back wrong and the tier may be why. READ THIS BEFORE WRITING ANY WORKFLOW SCRIPT: an agent() call with no agentType silently inherits the session's model and effort, and reviewer/builder are model:inherit, so three measured fan-outs ran 100% on Opus — one while passing agentType correctly on every call. Do not answer these from memory: a subagent that names no effort runs at the session's, Haiku is the cheap model and not the fast one, and a configured advisor is silently given to every subagent. Guessing costs time, quality and tokens."
license: MIT
---

# Delegate

Routing guidance for handing work to subagents, for **speed, result quality and cost,
together.** Read the ladder, stop at the first match, and only read further if that call
was close.

## If you are writing a Workflow script, read this first

**Every `agent()` call needs an `agentType`.** Nothing else in this file matters as much,
because this is the one mistake that has been measured three times:

| when | what happened |
|---|---|
| 2026-09-30 | an 81-agent fan-out passed `{label, phase, schema, effort}` at all four call sites. Every agent logged `agentType: "workflow-subagent"` and ran Opus. |
| 2026-09-30 | a 19-agent run passed `agentType: '…:reviewer'` correctly on 18 calls — and **still** ran all-Opus, because `reviewer` is `model: inherit`. |
| 2026-10-08 | four scripts, 13 `agent()` calls. 8 had no `agentType`; the other 5 were `reviewer`. **100% Opus again**, both failure modes at once, in a session that had this skill loaded. |

Those three ran on `claude-opus-5`. Two distinct causes, and you need both fixes:

1. **Omitting `agentType` is not a cheap tier — it is no tier.** It inherits the session's
   model **and** its effort, and loses the definition's `maxTurns`, tool allowlist,
   `omitClaudeMd`, operating rules and return-value contract. In an Opus session at
   `xhigh` that measured 6.2x the time and 6.6x the cost of `sonnet/medium` for the same
   score. **The Workflow tool's own canonical example omits `agentType` on its build
   stage** — that example is what gets copied, which is how this keeps happening.
2. **`reviewer` and `builder` are `model: inherit`.** They pin `high` effort on the
   *session's* model; they do not change the model. In an Opus session they are Opus.
   They are escalations; `inspector` and `drafter` are the defaults.

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
**Generation and verification are different jobs and must not share a tier** — a workflow
that runs every stage at the session tier is anti-pattern 14.

A `PreToolUse` hook ships with this plugin and **blocks** a `Workflow` whose `agent()`
calls have no `agentType`. If no shipped definition fits, put `// untiered: <reason>` on
or just above the call and name an `effort` on it — the hook warns when a waived call
names none. It fails open on anything it cannot parse: a backstop, not a gate to lean on.

## Route it in ten seconds

Answer the first question that hits. Stop there. Everything below is backing detail.

1. **Is this ONE target, and would the subagent keep most of what it reads?** →
   **do it inline.** It is a *volume* test, not a turn-count test ("digest this 60K-line
   changelog" is two tool calls and still belongs in a subagent), and a *single-target*
   test, not a "do I know the filenames" test ("apply this same edit to 12 board
   directories" names every file up front and is still a fan-out).
2. **Is an agent still live on this** — one you spawned with `run_in_background: true`,
   or any agent `ListAgents` shows? → **`SendMessage` it.** Its context is still warm, and
   it keeps everything it already read. (A synchronous Agent call that has already
   returned is not live: re-brief a fresh one.)
3. **Name the payoff you are buying** — context protection, tier arbitrage, or
   wall-clock parallelism. Can't name one? → **inline.** (Payoffs are not exclusive, and
   naming one here does not commit you to a cheap tier — see the note under rule 7.)
4. **One target, bounded question, big search, small answer?** → **one Agent call, with a
   tier named:** `inspector` for a read you will act on, `scout` when you can check the
   answer and cost matters. Do not omit `model` to "inherit" — that is the session's
   model at the session's effort, or a silent downgrade if `CLAUDE_CODE_SUBAGENT_MODEL`
   or a configured default is set. When an escalation predicate fires, `reviewer`
   (read-only) or `builder` (writes) inherit reliably and pin `high`.
5. **Three or more similar items, or more than one stage per item?** → **Workflow,
   `pipeline()`.** This beats rule 1 whenever they disagree — item count wins over
   "I know which files".
6. **Need a validated `schema`?** → **Workflow**, even for a single item. **This rule
   outranks 1 and 3**, the same way 5 does: rule 1 would call the job inline and rule 3
   finds no payoff in the list, but a `schema` is a correctness mechanism, not a payoff.
   A specific effort level is *not* a reason — the `Agent` tool takes `effort`.
7. **Still unsure?** → inline. The floor is higher than it feels.

**Precedence, when two rules fire:** 5 and 6 beat 1 and 3. Within those, answer in order.

**Losing tier arbitrage does not un-justify the delegation.** If a gate later disqualifies
the tier you had in mind, you do **not** fall back to inline — you step up one rung and
collect the other payoffs (parallelism, context protection) instead. **One rung, not to
the top:** failing the Haiku gate lands you on `drafter`/`inspector` (pinned Sonnet), not
on the session model; only an *escalation* predicate takes you to `builder`/`reviewer`.
Collapsing the two is how a fan-out that merely "needed more than Haiku" ends up on Opus.
Only the *tier* changes, never the *shape*: the ladder decides shape, then the predicates tier.

## The delegation floor

Every subagent starts cold: fresh system prompt, tool definitions re-sent, `CLAUDE.md`
re-injected, no conversation history. Its final report is **not shown to the user** —
you read it and relay it. So delegation never reduces total tokens; it relocates them
and adds some. It only saves you the tokens the subagent **discards**:

```
savings = D − (S + C + B + 2R)

D  tokens the subagent reads and throws away (never need to reach you)
S  its system prompt + tool definitions — NOT fixed: the `tools:` list controls it
C  CLAUDE.md, re-injected per subagent  — wc -c ~/.claude/CLAUDE.md ./CLAUDE.md, ÷4 ≈ tokens
B  the brief: every fact from this conversation you must restate, because it cannot see it
R  the report — counted TWICE (its output, then your input), three times if relayed verbatim
```

>  **`S` is the term you can actually move, and it tracks tool count — not model tier and
>  not project context.** A read-only `reviewer` on Opus has a smaller prefix than the
>  wider-tooled `worker` on Sonnet. Restricting `tools:` in a definition is the single
>  biggest input lever you have, bigger than `omitClaudeMd` and bigger than dropping a tier.

Measured prefixes and the paired A/B behind that claim are in
`references/model-selection.md` → "The tool surface is the biggest lever". The two numbers
you need to route *here*: budget `S + C` at **about 7-9k** for a scoped definition and
**about 38k** for an all-tools agent (measured 2026-10-09 on a one-line echo: 6,824-8,869
subagent tokens for the scoped tiers against 38,112 and 38,131 for `general-purpose`,
4.3-5.6x). **If D is not clearly larger than that cold start, do it inline.**

- **High D** — grepping a large tree for one fact, reading a long build log, scanning
  forty files to find the three that matter, driving a browser. Delegate these.
- **Low D** — anything whose output length approaches its input length: translating a
  paragraph, renaming a symbol, one function from a spec you'd have to write out anyway.
- **Long-form prose for the user is a bad delegation target.** You pay `R` twice, then
  reproduce it. Unless D is genuinely large, write it yourself.
- **`Explore` and `Plan` omit CLAUDE.md**, so their floor is lower. Route locate-only
  work there rather than to `general-purpose`.
- **Cut `S` first, then `C`.** A narrow `tools:` list is worth far more than
  `omitClaudeMd: true`, which runs a subagent without user, project and local CLAUDE.md.
  `mechanical` and `scout` ship with it set: a self-contained brief is their mandate, and
  a fan-out pays every cold start per agent. Never set it when the task depends on
  project conventions.
- **Specify the report's shape and length in the brief.** After D, `R` is the only term
  you control. A two-line verdict costs far less than a narrated summary, and arrives sooner.

You delegate to buy at least one of three things. Name one before you call — you often
get more than one, and losing a payoff later does not retract the others.

| Payoff | What you are buying | Test that decides it |
|---|---|---|
| Context protection | The conclusion without the bytes | Will you edit against these files? No → delegate |
| Tier arbitrage | Bulk work at Haiku's or Sonnet's rate instead of the session's — 1x or 20x on price where Opus is 40x | 3+ near-identical items with an objective done-condition |
| Wall-clock parallelism | Independent branches while the user waits | No item reads another item's output |

## The two boundaries

**Inline → one Agent.** The discriminator is *context asymmetry*: the search is large,
the answer is small. A grep that may touch forty files and returns one path is
delegation. A grep that returns the bytes you are about to edit is not — you would only
have to read them again.

**One Agent → Workflow.** Any one of these flips it:

- Three or more similar items. Concurrency is capped at `min(16, CPUs − 2)` per
  workflow (lifetime 1000) — a 40-item fan-out is not 40-way.
- More than one stage per item.
- You need a validated `schema`. This flips even a single item. (A specific `effort`
  does not: pass it on the `Agent` call.)

**All eight tiers work inside a Workflow too.** `agent()` takes `agentType`, so
`agent(prompt, {agentType: 'intelligent-delegate:drafter'})` gets that definition's model
and effort, and `effort` beside it adjusts that one call. Use `{model, effort}` with no
`agentType` only when no shipped definition fits; name both, and mark the call
`// untiered: <reason>` so the shipped hook passes it. Such an agent is logged as
`workflow-subagent` and gets none of a definition's limits or rules: `{effort: 'high'}` is
not `reviewer`, and `{model: 'haiku'}` is not `mechanical`. See
`references/workflow-patterns.md`, "Addressing a tier".

Inside a Workflow, `pipeline()` is the default — per-item streaming, no barrier. Reach
for `parallel()` only when stage N genuinely needs cross-item context from **all** of
stage N−1 (dedup, rank, early-exit on zero); "I need to flatten first" is not a reason.

**Isolation.** The criterion is not "does this agent write" — it is **can this agent's
inputs change while it runs, no matter who changes them.** Isolate when:

- two or more agents write the **same paths**; or
- any agent runs **git operations** (commit, checkout, stash, branch) — one index and
  one HEAD are shared across the checkout; or
- **you, the orchestrator, will keep editing files the agent is reading.** A read-only
  reviewer is *not* automatically safe: it has nothing to isolate *from itself*, but it
  is still reading a tree you are mutating.

Concurrent writes to **disjoint paths do not conflict** and need no worktree: twelve
agents each editing their own board directory are fine unisolated. A worktree costs setup
time plus disk *per agent*, so the default is off.

### Coordinating with agents you have already spawned

A subagent reading a file you are simultaneously rewriting will re-read, notice the
mismatch, and spend turns re-verifying — time and money, paid at that tier's rate, for
nothing. **Measured here:** a `reviewer` audit hit exactly this and spent 26 Bash calls,
most of them `git status` / `cat` / md5 churn establishing which version it was even
looking at. The protocol, in order of preference:

1. **Freeze, then brief.** Commit first, name the SHA in the brief ("review SKILL.md at
   `abc1234`"), and leave those files alone until the agent returns. Needs no worktree.
2. **Give the reader a worktree.** If you must keep editing, `isolation: 'worktree'`
   hands it a stable snapshot. Costs setup; buys independence.
3. **Batch your edits.** Queue changes and apply them after the read-only stage returns.
   Fan-out stages are short; your edits usually can wait.

Whichever you pick, **say in the brief which files are frozen and which are moving.** An
agent told "work from the SHA in your prompt, the tree is live" behaves; one that
discovers it by surprise burns turns proving the ground moved.

Script hygiene, because a dead script costs the whole run: `Date.now()`,
`Math.random()` and argless `new Date()` **throw**. `agent()` returns `null` on skip or
death — `.filter(Boolean)`.

## Effort, and how to actually reach it

**A subagent that names no effort runs at the *session's* effort, not at a default. Every
tier here pins one.** Call-site `effort` beats the definition's, which beats the
session's. Probed 2026-10-09 on Claude Code 2.1.295: a Haiku definition with no `effort:`
ran at `xhigh` in an `xhigh` session. Nothing falls back to the catalog's `default_effort`.

Effort is set in three places. The session's is what a call falls back to, and you cannot
set it from a call — which is the reason to leave nothing to it. The two you control:

1. **The definition.** Frontmatter `effort:`, reached by passing the definition's name as
   `subagent_type`, or as `agentType` in a Workflow. Honoured at runtime: a definition
   declaring `high` ran at `high` in an `xhigh` session.
2. **The call.** The `Agent` tool takes `effort` — `low|medium|high|xhigh|max` — and it
   overrides the definition's: a tier declaring `high`, called with `effort: 'low'`, ran
   at `low`. In a Workflow it is `agent(prompt, {agentType, effort})`. The tool's own rule
   is that effort is set only when the user or a skill asks. **This skill asks:** pass
   `effort` on any call that does not go through a pinned tier, and raise or lower a
   tier's effort at the call site instead of changing tier.

`max` is in every route's schema; one was run — a Workflow `{agentType, effort: 'max'}` ran
at `max` — and it was not in the sweep, so its time and cost are unmeasured. "Think hard"
in a prompt sets nothing — you get whatever those three gave and believe you tuned it.
`SKILL.md` frontmatter is **not** a fourth place: `effort:` there sets **the invoking
turn's** effort, never a subagent's, and it fails the `skill-creator` validator besides.

**`medium` is the default for bounded work on every model.** `low` saved 8-17% and is
where every Sonnet and Opus miss happened; `high` took 1.4-1.9x as long and `xhigh`
2.9-3.9x, and neither improved a score. Measured on saturated tasks: it shows `medium` is
enough for work of this difficulty and nothing about harder work. **Raise effort before
tier:** pass `effort: 'high'` on the call before you reach for a different tier. Change
tier on an escalation predicate, not on a feeling.

**A single Agent call reaches any model at any effort**, since `model` and `effort` are
both on it — but only a definition sets `tools`, `maxTurns` and `omitClaudeMd`, so name
the nearest tier and adjust it. haiku/low is `mechanical` (writes) or `scout` (read-only);
sonnet/medium is `worker` or `inspector`; sonnet/high is `drafter`, or `inspector` with
`effort: 'high'`; opus/xhigh is `judge`. The session model is `builder` with Edit/Write
and `reviewer` without: both pin `high` whatever the session is at — a raise in a `low`
session, a lowering in an `xhigh` one. Haiku takes effort like the rest: only
`claude-haiku-4-5`, whose catalog capability list is `["context_management"]`, with no
`"effort"`, takes none, and `haiku` resolves to `claude-haiku-5-5`.

The Agent tool's `model` enum is `haiku|sonnet|opus|fable` — there is **no `inherit`
value to pass**. Omitting `model` only *usually* inherits: it resolves to the **default
subagent model**, which `CLAUDE_CODE_SUBAGENT_MODEL` or a configured default can point
elsewhere, silently handing an Opus session a Haiku subagent. The **reliable** route is a
definition whose frontmatter says `model: inherit` literally — `reviewer` or `builder`.

**Lower effort before lowering model.** Effort trades thoroughness against time and spend
*within* one model — the judgment quality you rely on stays put and the cache stays
warm. Dropping a tier swaps the model and forfeits cache reuse, because caches are
model-scoped. It was also the larger speed lever measured — next section.

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

The levers, in the order they paid — check them in this order when a fan-out is slow:

1. **Effort.** The largest speed lever, larger than model. Against the same model at
   `medium`, `xhigh` took 2.9x (Haiku), 3.7x (Sonnet) and 3.9x (Opus) the time, and `high`
   1.4x, 1.5x and 1.9x. `low` was only 17%, 8% and 9% faster — stop at `medium`.
2. **Tier.** Sonnet is the fast model. Haiku is the cheap model, not the fast one: at
   `medium` it took 1.6x as long as Sonnet, because it writes about three times the output
   tokens. Opus at `medium` also took 1.6x as long and cost 2.4x as much, for the same
   score. An untiered call gets both levers wrong at once.
3. **Shape.** Judged, not measured by the sweep: a fan-out hides per-agent latency, which
   is where the Haiku tiers belong, and `pipeline()` has no barrier to wait behind.

47 of 48 task x arm cells scored 0.98 or better, so this is strong evidence about time and
cost and weak evidence about quality: it cannot show where the cheaper cells stop being
enough, and loosens no escalation predicate. **Not measured:** tokens per second, fast
mode, `max` effort, an advisor consult, any escalation-shaped task, or `judge`'s own work.

## Model tier: the two gates and their predicates

The price ladder: **Haiku 1x / Sonnet 20x / Opus 40x / Fable 100x, input and output
alike.** Between Haiku and Sonnet that is 20x on price, about 10x measured — Haiku writes
about three times the output tokens. Haiku 5.5 has a 1M window. Above 100K prompt tokens
it bills 5x its base rate, which is still a quarter of Sonnet's.

**The default depends on how many agents you are about to spawn.** "Inherit the session
model" is right for *one* delegated call that needs it and wrong for a fan-out — it is how
three measured runs cost Opus rates end to end.

- **One agent, and you need session-model judgment** → inherit (`reviewer` / `builder`).
  Pinning saves *one agent's worth*, while the risk of a wrong tier sits in the one result
  you will act on. Pin anyway when the job is plainly ordinary — on bounded work the
  pinned tiers scored the same as the Opus cells in less time (measured, saturated).
- **A fan-out, or any multi-stage Workflow** → **start at the pinned-Sonnet rung**
  (`drafter` to generate, `inspector` to verify) and escalate only the stages where an
  **escalation predicate** fires. Per-stage escalation is the point of a Workflow; a
  uniform session-model fan-out pays top-tier price and latency on every clerical stage.

### Two gates, not one — read this before using the predicates

There are **two** tier decisions below and they do not share a test. Conflating them is
how you end up back at an all-session-model fan-out:

| Gate | The question | The list to use |
|---|---|---|
| **Escalation gate** | pinned Sonnet → the session model? | the *escalation* predicates, next. Narrow, because pinned Sonnet is already a judgment-capable tier, and `effort: 'high'` on the call is the step before it |
| **Haiku gate** | Sonnet → `mechanical` or `scout`? | the *detectability* gate and the no-downgrade predicates after it. Strict: what a miss costs there is not the retry, it is not noticing |

**The verb is not an escalation trigger.** "The verb is *review, audit, assess*" is a
sound reason not to send work to **Haiku**. It is **not** a reason to escalate to the
session model, because `inspector` — pinned Sonnet, read-only — exists precisely to do
review work; read as an escalation trigger it routes every inspection stage to `reviewer`.
**Judgment work is the pinned rung's job; only the escalation predicates take it off.**

**Escalation — pinned Sonnet to the session model. Any ONE is enough:**

- **Two readings of the brief survive a careful read.** If you cannot tell, that is the
  second reading surviving. ("Apply the same edit to each": an identical literal diff, or
  the same *kind* of change per target?) **Kill one first if you can** — ask, or read one
  target; across a fan-out that beats escalating every item, and you tier by the answer.
- **Correctness rests on an invariant not written in the brief** — a codebase convention,
  a lock ordering, a schema constraint the agent would have to infer.
- **The deliverable contains a negative or universal claim** — "no other callers",
  "nothing else writes this field". Absence proofs need exhaustive reading.
- **Blast radius is security, auth, money, deletion, migrations or concurrency.**
- **Failure would be silent to you**, or you will build many turns on the result without
  re-checking it. **Escalate on blast radius, not on difficulty:** the cost of being wrong
  is then not a retry, it is the whole branch built on top.

Nothing else earns it. Not "this one matters", not the verb, not wanting more
thoroughness on a bounded check — that is `effort: 'high'` on the call — and not a long
input: a large read is a reason to *delegate*, and on the extraction task Sonnet and Opus
each got 200 of 200 answers. One more shape earns it: **one cross-cutting pass over every
item at once** — one agent, not one per item. Fanning an inherit tier across items *with no
predicate firing on them* is anti-pattern 14; an ambiguity you could not kill is exempt.

**The Haiku gate is detectability.** A failed Haiku attempt is nearly free in dollars.
What it costs is the wall-clock of the failed attempt and the risk nobody notices. So the
gate on a Haiku tier is whether you can tell, quickly, that the result is wrong.

**No-downgrade to Haiku — any ONE of these is disqualifying,** because each is a way a
wrong result arrives looking like a right one. Input size is not among them:

- **Any escalation predicate above.** A cheap tier resolves ambiguity by silently picking
  a reading, infers no unstated invariant, and stops early on an absence proof and
  asserts anyway. If the brief does not settle it, do not downgrade.
- **The verb is *review, audit, assess, decide, is-this-safe, did-I-miss*.** Judgment
  tasks have no deterministic check. **Haiku-gate only** — it says such work does not
  belong on a Haiku tier, not that it needs the session model. Its home is `inspector`.
- **Failure would be silent to you.** No detection means no cheap tier.

**Safe-downgrade — ALL must hold:** the work is specified by rule or example
(`mechanical`) or is the extraction of named facts (`scout`); items are homogeneous;
output is validated by something deterministic you **will actually run**, or by quoted
evidence you will actually read; a failure is detectable at a glance, not by redoing it.

**The retry math.** Judge cost per *completed task*, not per request. Going cheap-first
is cheaper only while the first-pass failure rate `p` stays under

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
happens. On price, a Haiku attempt that fails and is retried on Sonnet is 21 units against
20, so a cheap first attempt is nearly free in dollars. What it costs is **wall-clock** —
the failed attempt's latency is paid before the retry starts — and **the risk that the
failure is not noticed at all**, where no table applies.

**Route the check with the task**, in this order: (1) **deterministic** — a Workflow
`schema`, a test, a build, a grep; zero model cost, and a `schema` on every stage whose
output feeds another stage is free validation at the seam; (2) **caller reads it** —
only when the report is small; (3) **adversarial pass** — hand `inspector`, or `reviewer`
on a predicate, the artifact *and* the brief and ask it to find the failure. "Confirm this
is correct" gets you agreement; "find what is wrong with this" gets you review.

## The advisor makes every tier price a floor

**Observed 2026-09-30, one session:** every subagent it spawned received an
`advisor_tool` attachment with `available: true` and `model: claude-fable-5-1` — the
100x rung of the price ladder. That included `mechanical`, the 1x rung. Seen again
2026-10-09 in all nine probe transcripts and all 240 sweep runs, none of which called it.
The advisor *model* is session configuration, not a harness constant — the model catalog
assigns an `advisor_rank` per model, so another session resolves a different one.

This is session-scoped, not per-agent. The advisor is configured once for the
conversation (`/advisor`, `/advisor <model>`, `/advisor off`, or `--advisor` at launch)
and is then injected into every subagent the session spawns. Consequences:

- **A tier's own price is a floor, and an advisor call silently undoes a downgrade.** The
  point of pinning `mechanical` or `worker` is to spend less than the session model; a
  Fable consult inverts that, and nothing in the tier's own definition prevents it. What
  a consult adds in dollars or seconds has not been measured here.
- **Per-agent suppression is impossible, not merely untested.** Verified in the CLI
  binary: the advisor spec (`advisor_20260301`) is appended to the wire `tools` array
  *after* the client tool list, gated only on whether an advisor model resolved, and it
  executes **server-side** (`server_tool_use` → `advisor_tool_result`). It never passes an
  agent's allow/deny filter or a permission hook. `disallowedTools: [advisor]` is a no-op.
- **The controls that do work are session-wide:** `/advisor off`, or the environment
  variable `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` for non-interactive and scripted runs.
- **It is not always wrong.** On `judge` or `reviewer` — tiers whose job is correctness —
  a stronger second opinion is the point. On a bulk `mechanical` fan-out it is cost inversion.

**If you are fanning out many cheap agents and cost predictability matters, ask the user to
turn the advisor off for that session** — `/advisor off` is a slash command only they can
issue, and exporting `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` inside a `Bash` call affects only
that subprocess, not the session that spawns your agents. Until they do, **price the fan-out
at the advisor's tier, not the agent's.** That pricing half is always actionable by you.

### `disallowedTools` is ignored whenever `tools:` is set

A second verified gotcha, and it applies to every definition you write: the frontmatter
schema says `disallowedTools` is *"Tools removed from the default set. **Ignored if
`tools` is set.**"* `tools:` is an allowlist that **replaces** the default set, so listing
both means the deny list does nothing — anything absent from `tools:` is already gone.
**Pick one mechanism.** A deny list under an allowlist reads as a control and is not one.

## Fable

**Never set `model: "fable"` on a subagent** — though note the section above: if an
advisor is configured, your subagents can already *reach* Fable, so this rule is about
not paying Fable rates for every token a subagent emits. The argument is structural:

- Fable is the top of the price ladder — 100x Haiku, 5x Sonnet, 2.5x Opus — and a
  subagent's output is *intermediate*: you read it, compress it, then relay it.
- If your session model is not Fable, you are asking a subagent to outperform the model
  that will grade its work. You cannot verify the upside, so you are paying that premium
  for an improvement you are structurally unable to detect.
- If your session model *is* Fable, inheriting already gives you Fable.
- Caches are model-scoped; a lone Fable subagent in a non-Fable session forfeits reuse.

If the subagent's raw output *is* the entire deliverable, do it in the main loop where
you can iterate — not behind a one-shot Agent call you can only accept or re-run.

## Agent type

Shipped definitions are namespaced: `intelligent-delegate:mechanical`, and so on — eight
tiers. The figures are from the 2026-10-09 sweep, measured on saturated tasks (see "Speed").

| type | route here for | never route here for |
|---|---|---|
| `Explore` | locating — which files, where defined, does X exist. Omits CLAUDE.md, cheapest cold start | **review, audit, or absence proofs.** It reads excerpts — an excerpt cannot establish a bug is *not* there |
| `Plan` | step-by-step plans, critical-file lists. No write tools; omits CLAUDE.md | execution |
| `general-purpose` | open-ended multi-step, full tool access | anything a tiered definition covers more precisely |
| `mechanical` (haiku/low, writes) | homogeneous work specified by rule or example — renames, format fixes, record conversion — in a fan-out, where parallelism hides its latency. Measured on the transform task: a tenth of `worker`'s cost, 1.4x its time, every record right | anything with a judgment step; one latency-sensitive call — `worker` is faster; **anything needing an MCP tool** — neither Haiku tier lists `ToolSearch`, deliberately |
| `scout` (haiku/low, read-only) | pulling named facts out of a large input **when you can check the answer** or a wrong one is cheap — counting or locating log entries, extracting fields, finding which files mention something. Not a stage default. On the extraction task: $0.0027 a run against `sonnet/medium`'s $0.0356 at about the same speed, and 48 of 50 answers right where every Sonnet and Opus run got them all (measured as Haiku at `low` on `inspector`'s definition, not on `scout`'s own) | review, audit, an absence proof or any verdict; one read you will act on unchecked — `inspector`; MCP work |
| `worker` (sonnet/medium, writes) | well-specified implementation with a deterministic check attached. The fastest cell measured with no misses | ambiguous specs — it will pick a reading and commit |
| **`drafter` (sonnet/high, writes)** | **the default generation tier.** Producing an artifact from source material you supply: documentation from an evidence file, a runbook, a well-scoped implementation, a pattern applied with per-target adaptation | genuine ambiguity, or a silent-failure blast radius — that is `builder`. Fully specified output — `worker`, 41% faster on a spec-driven implementation at the same score |
| **`inspector` (sonnet/medium, read-only)** | **the default inspection tier.** Ordinary review, verification and audit — checking an artifact against its source, verifying one finding, per-item correctness in a fan-out — and a read whose answer you will act on. At `medium` it found every seeded defect in every run, 39% faster than at `high` — on a saturated task, so that says nothing about harder review; pass `effort: 'high'` when a bounded review needs more | negative/universal claims, security-auth-money blast radius, or a verdict carrying many turns — that is `reviewer` |
| `reviewer` (**inherit**/high) | the **escalation** above `inspector`: absence proofs, an invariant the brief does not state, the one verdict that gates the result | ordinary review — in an Opus session it measured 3.2x the time and 4.0x the cost of `inspector` on a bounded review, for the same result. Producing the fix — that is `builder` |
| `builder` (**inherit**/high, **writes**) | the **escalation** above `drafter`: two readings genuinely survive, unsafe-to-downgrade blast radius, failure would be silent | fully specified work — `worker`; ordinary generation — `drafter`, against which it measured 2.4x the time and 3.4x the cost in an Opus session for the same result. (In a Sonnet session `drafter` and `builder` are the same thing; in a Haiku session the inherit tiers are the cheaper ones) |
| `judge` (opus/xhigh) | the call you cannot afford to get wrong, or breaking a tie between two verdicts | routine work — its cell was the slowest and most expensive measured, 6.2x the time and 6.6x the cost of `worker`'s on bounded work for the same score |

**Routing MCP work.** MCP tools arrive deferred and `ToolSearch` loads them, so a tier must
list `ToolSearch` to reach one — `worker`, `drafter`, `inspector`, `reviewer`, `builder`
and `judge` all do; `mechanical` and `scout` do not, because an MCP response is unbounded
and shaped by a third party, and neither tier's mandate describes work against one. That
is necessary, not sufficient: a session can disable `ToolSearch` outright, subagents
inherit the disable, and then no tier reaches MCP and only the user can change it.
Before concluding a tier "cannot do MCP", read the error — a bare
`No such tool available: X` means the name is not registered, while a trailing
"disabled for this session, in subagents as well as here" means the session is the blocker.
`references/model-selection.md` → "Reaching MCP tools from a tier" has the full table.

## Anti-patterns

1. **Delegating context you already loaded.** D = 0. You pay `S + C + B + 2R` for nothing.
2. **A fresh Agent call to ask a follow-up.** Use `SendMessage`.
3. **Asking for effort in the prompt text.** "Think hard" sets nothing. Pass `effort` on
   the call, or name the tier that pins the level you want.
4. **Routing to a Haiku tier for speed, or for a read you will not check.** Haiku is the
   cheap model, not the fast one: at `medium` it took 1.6x as long as Sonnet.
   A large input is not the obstacle; an unchecked answer is.
5. **Using `Explore` to answer a correctness question.** It locates; it does not audit.
6. **`parallel()` where `pipeline()` works.** Every item now waits for the slowest.
7. **Skipping verification on work you will ship.** The review costs less than the incident.
8. **Building a multi-model cascade before measuring the best model at lower effort.**
   The cascade forfeits cache reuse across its models.
9. **Not relaying the report.** The user never sees it. An unrelayed result did not happen.
10. **Spawning an all-tools agent for a narrow job.** `general-purpose` re-sends every
    tool schema on every request — about 38k of cold-start prefix against about 7-9k for
    a scoped definition. Reaching for it repeatedly? Ship a definition with a narrow `tools:`.
11. **Editing files an agent you spawned is reading.** Commit first and pin the SHA in the
    brief, or give it a worktree. Read-only does not mean collision-free.
12. **Assuming the tier price is the total.** If an advisor is configured for the
    session, every subagent can reach it — here, Fable, the 100x rung. Price the floor.
13. **Silent caps.** If you bound coverage — top-N, no-retry, sampling — say what was
    dropped. Silent truncation reads as "covered everything" when it didn't.
14. **A uniformly-tiered fan-out.** The habit with three measurements behind it. If every
    stage carries the same tier — or no tier — you are paying generation prices and
    latency for clerical work and clerical prices for the call that decides whether the
    output is right. Per-stage tiering is the whole reason to reach for a Workflow.
15. **Reading `model: inherit` as "the cheap option".** `reviewer` and `builder` pin
    `high` effort; they do not change the model. In an Opus session they are Opus. The
    pinned-Sonnet rung (`inspector`, `drafter`) is the actual downgrade.
16. **Leaving effort unset.** The agent runs at the session's effort, not at a default:
    Haiku at an inherited `xhigh` measured 2.5x slower than at `low`, for the same score.
17. **Raising effort on bounded work.** `high` and `xhigh` cost time and improved no score
    (see "Effort"). Raise it for a reason you can name, on the one call that has it.

## References

- `references/model-selection.md` — the cost table, worked spend and break-evens, "The
  measured grid", "The 100K price cliff", cascade-vs-single-model, how to set each knob.
- `references/workflow-patterns.md` — barrier decision, named fan-out shapes, per-stage tiering.
- `references/agent-catalog.md` — every `subagent_type` with its model, effort, tool
  surface, and use/don't-use lines.
- `evals/tier-sweep/RESULTS.md` — every measured figure quoted here, per task.
