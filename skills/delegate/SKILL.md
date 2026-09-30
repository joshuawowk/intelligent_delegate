---
name: delegate
description: Decide whether to delegate a task at all, what shape to use (inline, one subagent, or a Workflow fan-out), and which model tier and reasoning effort to spend on it. Use when about to spawn agents, parallelize, fan out, or orchestrate subagents; when choosing a model or effort level for a subagent; when work feels too expensive, too slow, or too token-hungry; when deciding if a cheaper model would do; or when a delegated result came back wrong and the tier may be why.
license: MIT
---

# Delegate

Routing guidance for handing work to subagents. Read the ladder, stop at the first
match, and only read further if that call was close.

## Route it in ten seconds

Answer the first question that hits. Stop there. Everything below is backing detail.

1. **Is this ONE target, and would the subagent keep most of what it reads?** →
   **do it inline.** Being able to *name* the files is not enough on its own: twelve
   files you can name is still a fan-out, so count targets before you take this exit.
2. **Is an agent already running on this?** → **`SendMessage` it.** Never open a fresh
   Agent for a follow-up; its context is still warm.
3. **Name the payoff you are buying** — context protection, tier arbitrage, or
   wall-clock parallelism. Can't name one? → **inline.** (Payoffs are not exclusive, and
   naming one here does not commit you to a cheap tier — see the note under rule 7.)
4. **One target, bounded question, big search, small answer?** → **one Agent call.**
   Omit `model`.
5. **Three or more similar items, or more than one stage per item?** → **Workflow,
   `pipeline()`.** This beats rule 1 whenever they disagree — item count wins over
   "I know which files".
6. **Need a specific effort level or a validated `schema`, and no shipped definition
   fits?** → **Workflow**, even for a single item. That is the only other door.
7. **Still unsure?** → inline. The floor is higher than it feels.

**Losing tier arbitrage does not un-justify the delegation.** If you named tier arbitrage
at rule 3 and the safe-downgrade gate later disqualifies the cheap tier, you do **not**
fall back to inline — you delegate at the inherited model and collect the other payoffs
(parallelism, context protection) instead. Only the *tier* changes, never the *shape*.
Shape is decided by the ladder; tier is decided by the predicates, and they are
independent questions answered in that order.

Two ways rule 1 misfires, both worth memorising:

- **It is a *volume* test, not a turn-count test.** "Digest this 60K-line changelog" is
  two tool calls and still belongs in a subagent — the volume is the point.
- **It is a *single-target* test, not a "do I know the filenames" test.** "Apply this
  same edit to 12 board directories" names every file up front and is still a fan-out.
  When rule 1 and rule 5 disagree, **rule 5 wins.**

## The delegation floor

Every subagent starts cold: fresh system prompt, tool definitions re-sent, `CLAUDE.md`
re-injected, no conversation history. Its final report is **not shown to the user** —
you read it and relay it. So delegation never reduces total tokens; it relocates them
and adds some. It only saves you the tokens the subagent **discards**:

```
savings = D − (S + C + B + 2R)

D  tokens the subagent reads and throws away (never need to reach you)
S  its system prompt + tool definitions — NOT fixed: the `tools:` list controls it,
   and it is usually the largest term you can actually move (see below)
C  CLAUDE.md, re-injected per subagent  — wc -c ~/.claude/CLAUDE.md ./CLAUDE.md, ÷4 ≈ tokens
B  the brief: every fact from this conversation you must restate, because it cannot see it
R  the report — counted TWICE (its output tokens, then your input tokens to read it),
   three times if you relay it to the user verbatim
```

**Controlled A/B on this harness.** `mechanical` vs `general-purpose` with `model: "haiku"`
pinned on both — verified from the transcripts that both ran `claude-haiku-4-5`, same
prompt, byte-identical output. Only the definition differed:

| agent | tools | CLAUDE.md | cold-start prefix | total input, 9 requests |
|---|--:|:--:|--:|--:|
| `mechanical` | 6 | omitted | **7.5k** | **98k** |
| `general-purpose` | all | kept | **42.4k** | **435k** |

**4.4× for the same answer**, and CLAUDE.md is only ~500 tokens of the 34.9k prefix gap —
the rest is tool schemas, re-sent every request.

For scale, the prefix of each shipped tier as actually measured (these run *different*
models, so read the column as prefix-by-tool-surface, not as a controlled comparison):

| agent | tools | CLAUDE.md | model run | cold-start prefix |
|---|--:|:--:|---|--:|
| `reviewer` | 4 | kept | `claude-opus-5` | **6.8k** |
| `mechanical` | 6 | omitted | `claude-haiku-4-5` | **7.5k** |
| `worker` | 8 | kept | `claude-sonnet-5` | **12.0k** |
| `general-purpose` | all | kept | (as passed) | **42.4k** |

Prefix tracks tool count, not model tier and not project context — `reviewer` is the
most expensive *model* here and still has the smallest prefix, on four tools. So:

> **Restricting `tools:` in an agent definition is the single biggest token lever
> available to you** — bigger than `omitClaudeMd`, bigger than dropping a model tier.
> Give each definition only the tools its job needs.

Budget `S + C` at **~7–12k** for a scoped definition (4–8 tools, as measured above) and
**~40k+** for an all-tools agent. Practical break-even: **if D is under ~15k tokens, do it inline** —
and note that an all-tools agent has already spent more than that before it reads
anything.

- **High D** — grepping a large tree for one fact, reading a long build log, scanning
  forty files to find the three that matter, driving a browser. Delegate these.
- **Low D** — anything whose output length approaches its input length. Translating a
  paragraph, renaming a symbol, writing one function from a spec you'd have to write
  out anyway. The brief costs as much as the work. Inline.
- **Long-form prose for the user is a bad delegation target.** You pay `R` twice, then
  reproduce it. Unless D is genuinely large, write it yourself.
- **`Explore` and `Plan` omit CLAUDE.md**, so their floor is lower. Route locate-only
  work there rather than to `general-purpose`.
- **Cut `S` first, then `C`.** A narrow `tools:` list is worth ~70× what `omitClaudeMd`
  is (34k vs 0.5k in the measurement above). Do both, in that order.
- **You can zero out `C` yourself.** `omitClaudeMd: true` in an agent definition runs that
  subagent without user, project and local CLAUDE.md. Worth it when the brief is
  self-contained — `mechanical` ships with it set, because `C` is spent inside Haiku's
  200K wall. Never set it when the task depends on project conventions.
- **Specify the report's shape and length in the brief.** After D, `R` is the only term
  you control. A two-line verdict costs a fifth of a narrated summary.

You delegate to buy at least one of three things. Name one before you call — you often
get more than one, and losing a payoff later does not retract the others.

| Payoff | What you are buying | Test that decides it |
|---|---|---|
| Context protection | The conclusion without the bytes | Will you edit against these files? No → delegate |
| Tier arbitrage | Bulk mechanical work at 1×/2× instead of your 5× | 3+ near-identical items with an objective done-condition |
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
- You need `effort` or a validated `schema` and no shipped definition provides it.
  This flips even a single item.

**The four tiers work inside a Workflow too.** `agent()` takes `agentType`, so
`agent(prompt, {agentType: 'intelligent_delegate:worker'})` gets that definition's model
and effort — the same tiers, one parameter over. Use `{model, effort}` directly only when
no shipped definition fits, or when you need `max` effort.

Inside a Workflow, `pipeline()` is the default — per-item streaming, no barrier. Reach
for `parallel()` only when stage N genuinely needs cross-item context from **all** of
stage N−1 (dedup, rank, early-exit on zero). "I need to flatten first" is not a reason;
do it inside a stage. See `references/workflow-patterns.md`.

**Isolation.** Set `isolation: 'worktree'` only when concurrent agents would *actually
conflict* — they write the **same paths**, or any of them runs **git operations**
(commit, checkout, stash, branch), which share one index and HEAD across the checkout.

Concurrent writes to **disjoint paths in one tree do not conflict** and do not need it:
twelve agents each editing their own board directory are fine unedited. Worktrees cost
~200-500ms plus disk *per agent*, so the default is off. Never set it on a read-only
stage — a reviewer or judge has nothing to isolate.

Script hygiene, because a dead script costs the whole run: `Date.now()`,
`Math.random()` and argless `new Date()` **throw**. `agent()` returns `null` on skip or
death — `.filter(Boolean)`.

## Effort, and how to actually reach it

**The Agent tool has no `effort` parameter.** Writing "think hard" or "use high effort"
in the prompt does nothing — you get the default and believe you tuned it. Effort is
reachable exactly two ways:

1. **A shipped agent definition** whose frontmatter sets `effort:` — then pass its name
   as `subagent_type`. Frontmatter accepts `low|medium|high|xhigh`. **No `max`.**
2. **A Workflow**: `agent(prompt, { effort })` — `low|medium|high|xhigh|max`. `max` is
   Workflow-only.

`SKILL.md` frontmatter is **not** a third route. `effort:` there is honoured by this
harness, but it sets **the invoking turn's** effort — not a subagent's. It is also absent
from the published Agent Skills spec and fails the `skill-creator` validator, so it does
not travel. Never route a subagent on it.

A bare Agent call runs at **the session's** effort, whatever that is — the Agent tool
gives you no way to raise or lower it. Defaults are per-model and change between releases,
so do not assume a level; if a stage needs a specific one, that is a `subagent_type` or a
Workflow, not a prompt instruction.

`xhigh` suits most coding and agentic work; `high` is the usual sweet spot between quality
and token efficiency, and is the better default when you are paying for many subagents.
`low` means fewer, more-consolidated tool calls and less preamble — good for simple or
high-volume subagent work.

**What is actually reachable from a single Agent call:**

| you want | reachable? | how |
|---|---|---|
| session model, session effort | usually | omit `model` — but this yields the *default subagent model*, which `CLAUDE_CODE_SUBAGENT_MODEL` or a configured default can override |
| session model, `high` | yes | `reviewer` — **the only shipped definition that moves effort without moving model** |
| session model, `medium` or `low` | **no** | Workflow, or ship a 5-line definition file |
| session model **with Edit/Write** | **no** | `reviewer` inherits but is read-only. Use a Workflow (`agent(prompt, {effort})`, no `model` key), or ship a definition — no shipped tier covers inherit-plus-write |
| haiku / low | yes | `mechanical` |
| sonnet / medium | yes | `worker` |
| opus / xhigh | yes | `judge` |
| anything at `max` | **no** | Workflow only |

The Agent tool's `model` enum is `haiku|sonnet|opus|fable` — there is **no `inherit`
value to pass**. Omitting `model` only *usually* inherits: it resolves to the **default
subagent model**, which `CLAUDE_CODE_SUBAGENT_MODEL` or a configured default can point
elsewhere. With `CLAUDE_CODE_SUBAGENT_MODEL=haiku`, "omit to inherit" silently hands an
Opus session a Haiku subagent — the exact downgrade this section exists to prevent. The
**reliable** route is `reviewer`, whose frontmatter says `model: inherit` literally.

**Lower effort before lowering model.** Effort trades thoroughness against spend
*within* one model — the judgment quality you rely on stays put and the cache stays
warm. Dropping a tier swaps the model and forfeits cache reuse, because caches are
model-scoped.

## Model tier: the no-downgrade predicates

Output-token cost is the number to reason with: **Haiku 1× / Sonnet 2× / Opus 4–5× /
Fable 10×.** (`opus` is an alias for your configured default Opus, which spans two priced
rows — Opus 5.5 at 4×, Opus 5 at 5×. Pin the full id when a budget turns on the difference.) Default: **inherit the session model.** Depart only with high confidence,
which means evaluating the predicates below rather than waving at them.

**No-downgrade — any ONE of these is disqualifying:**

- Two readings of the brief survive a careful read. Cheap tiers resolve ambiguity by
  silently picking one and proceeding confidently. **If you cannot tell whether two
  readings survive, that is itself the second reading surviving** — the predicate fires.
  ("Apply the same edit to each" is the classic case: an identical literal diff, or the
  same *kind* of change adapted per target? If the brief does not settle it, do not
  downgrade.)
- Correctness rests on an invariant **not written in the brief** — a codebase
  convention, a lock ordering, a schema constraint it would have to infer.
- The verb is *review, audit, assess, decide, is-this-safe, did-I-miss*. Judgment tasks
  have no deterministic check, so a wrong answer arrives looking exactly like a right one.
- The deliverable contains a **negative or universal claim** — "no other callers",
  "nothing else writes this field". Absence proofs require exhaustive reading; a cheap
  tier stops early and asserts anyway.
- Blast radius is security, auth, money, deletion, migrations, or concurrency.
- Material exceeds ~150K tokens after cold-start overhead — **Haiku's 200K context is a
  hard wall**, and `S + C` is spent inside it. Applies to `mechanical` by construction.
- **Failure would be silent to you.** No detection means no cheap tier.

**Safe-downgrade — ALL must hold:** the transformation is specified by example; items
are homogeneous; output is validated by something deterministic you **will actually
run**; a failure is detectable in under ~1k tokens of your reading.

**The retry math.** Judge cost per *completed task*, not per request. Going cheap-first
is cheaper only while the first-pass failure rate `p` stays under

```
p* = (dear − cheap) / (dear + d)

   d = your cost to notice the failure and re-brief, in the SAME absolute units as the
       multipliers (1 unit = one Haiku-equivalent). It is your own reading cost, so it
       does not scale with the tier under test — keep it absolute, not "one cheap run".
```

| cheap → dear | `d` = 0 (free detection) | `d` = 1 unit (realistic) |
|---|:--:|:--:|
| haiku → sonnet | 0.50 | **0.33** |
| sonnet → opus (4×) | 0.50 | **0.40** |
| sonnet → opus (5×) | 0.60 | **0.50** |

`d = 0` assumes you spot the bad result for free, which you never do — use the right-hand
column and then demand margin on top, because `d` is estimated, a retry also costs
wall-clock, and **failure you cannot detect makes the whole table inapplicable**.
**Haiku that fails once is more expensive than Sonnet that succeeds.**

**Escalate on blast radius, not on difficulty.** When failure is silent — a review you
will trust, a plan you will build twenty turns on — the cost of being wrong is not a
retry, it is the whole branch built on top.

**Route the check with the task**, in this order: (1) **deterministic** — a Workflow
`schema`, a test, a build, a grep; zero model cost, and a `schema` on every stage whose
output feeds another stage is free validation at the seam; (2) **caller reads it** —
only when the report is small; (3) **adversarial pass** — hand `reviewer` the artifact
*and* the brief and ask it to find the failure. "Confirm this is correct" gets you
agreement; "find what is wrong with this" gets you review.

## Fable

**Never set `model: "fable"` on a subagent.** The argument is structural:

- The 10× premium is on **output**, and a subagent's output is *intermediate* — you
  read it, compress it, then relay it.
- If your session model is not Fable, you are asking a subagent to outperform the model
  that will grade its work. You cannot verify the upside, so you are paying 10× for an
  improvement you are structurally unable to detect.
- If your session model *is* Fable, inheriting already gives you Fable.
- Caches are model-scoped; a lone Fable subagent in a non-Fable session forfeits reuse
  both ways.

If the subagent's raw output *is* the entire deliverable, do it in the main loop where
you can iterate — not behind a one-shot Agent call you can only accept or re-run.

## Agent type

Shipped definitions are namespaced: `intelligent_delegate:mechanical`, and so on.

| type | route here for | never route here for |
|---|---|---|
| `Explore` | locating — which files, where defined, does X exist. Omits CLAUDE.md, cheapest cold start | **review, audit, or absence proofs.** It reads excerpts — an excerpt cannot establish a bug is *not* there |
| `Plan` | step-by-step plans, critical-file lists. No write tools; omits CLAUDE.md | execution |
| `general-purpose` | open-ended multi-step, full tool access | anything a tiered definition covers more precisely |
| `mechanical` (haiku/low) | homogeneous, specified-by-example edits on small inputs | anything near 150K; anything with a judgment step |
| `worker` (sonnet/medium) | well-specified implementation with a deterministic check attached | ambiguous specs — it will pick a reading and commit |
| `reviewer` (inherit/high) | adversarial verification and code review — judgment at session-model quality for less spend | producing the fix |
| `judge` (opus/xhigh) | the call you cannot afford to get wrong, or breaking a tie between two verdicts | routine implementation |

## Anti-patterns

1. **Delegating context you already loaded.** D = 0. You pay `S + C + B + 2R` for nothing.
2. **A fresh Agent call to ask a follow-up.** Use `SendMessage`.
3. **Asking for effort in the prompt text.** The Agent tool has no `effort` parameter,
   and "think hard" is not one either. Ship a definition or use a Workflow.
4. **Routing a large read to `mechanical`.** The 200K wall is hard and cold-start spends
   into it. The symptom is truncation you never see, summarized confidently.
5. **Using `Explore` to answer a correctness question.** It locates; it does not audit.
6. **`parallel()` where `pipeline()` works.** You bought a barrier and every item now
   waits for the slowest.
7. **Skipping verification on work you will ship.** The reviewer pass costs less than
   the incident.
8. **Building a multi-model cascade before measuring the best model at lower effort.**
   The cascade forfeits cache reuse across its models.
9. **Not relaying the report.** The user never sees it. An unrelayed result did not happen.
10. **Spawning an all-tools agent for a narrow job.** `general-purpose` re-sends every
    tool schema on every request. Measured here: 42k of cold-start prefix versus 7.5k for
    a 6-tool definition, for the same answer. If you find yourself reaching for
    `general-purpose` repeatedly, ship a definition with a narrow `tools:` list instead.
11. **Silent caps.** If you bound coverage — top-N, no-retry, sampling — say what was
    dropped. Silent truncation reads as "covered everything" when it didn't.

## References

- `references/model-selection.md` — cost tables, priced fan-outs, the effort × model
  grid, cascade-vs-single-model, and how to set each knob.
- `references/workflow-patterns.md` — barrier decision, the named fan-out shapes, and
  per-stage tiering.
- `references/agent-catalog.md` — every `subagent_type` with its model, effort, tool
  surface, and use/don't-use lines.
