---
name: delegate
description: Route work to the right execution shape and tier — inline, one subagent, or a Workflow fan-out — and which model and reasoning effort each one gets. Use whenever delegation, parallelism, subagents, or agent cost comes up, including short asks like "should I delegate this or do it inline", "which model for these agents", "what effort level", "fan this out", "run these in parallel", "spawn some agents", "this is burning too many tokens", "can something cheaper do it", "Workflow or one Agent call", "is the overhead worth it", or when a delegated result came back wrong and the tier may be why. READ THIS BEFORE WRITING ANY WORKFLOW SCRIPT: an agent() call with no agentType silently inherits the session model, and reviewer/builder are model:inherit, so three measured fan-outs ran 100% on Opus — twice while passing agentType correctly. Do not answer these from memory. The Agent tool has no effort parameter, Haiku silently ignores effort settings, and when the session has an advisor configured every subagent silently gets it, which can invert the saving you delegated for. Guessing costs real tokens.
license: MIT
---

# Delegate

Routing guidance for handing work to subagents. Read the ladder, stop at the first
match, and only read further if that call was close.

## If you are writing a Workflow script, read this first

**Every `agent()` call needs an `agentType`.** Nothing else in this file matters as much,
because this is the one mistake that has been measured three times:

| when | what happened |
|---|---|
| 2026-09-30 | an 81-agent fan-out passed `{label, phase, schema, effort}` at all four call sites. Every agent logged `agentType: "workflow-subagent"` and ran Opus. |
| 2026-09-30 | a 19-agent run passed `agentType: '…:reviewer'` correctly on 18 calls — and **still** ran all-Opus, because `reviewer` is `model: inherit`. |
| 2026-10-08 | four scripts, 13 `agent()` calls. 8 had no `agentType`; the other 5 were `reviewer`. **100% Opus again**, both failure modes at once, in a session that had this skill loaded. |

Two distinct causes, and you need both fixes:

1. **Omitting `agentType` is not a cheap tier — it is no tier.** It inherits the session
   model and loses the definition's `maxTurns`, tool allowlist, `omitClaudeMd`, operating
   rules and return-value contract. **The Workflow tool's own canonical example omits
   `agentType` on its build stage** — that example is the thing that gets copied, so
   copying it is how this keeps happening.
2. **`reviewer` and `builder` are `model: inherit`.** They raise *effort*, not thrift. In
   an Opus session they are Opus. They are escalations; `inspector` and `drafter` are the
   defaults.

**Default tier by stage kind.** Start here and depart with a reason:

| the stage | tier | what it is |
|---|---|---|
| generate / draft prose or code | `intelligent-delegate:drafter` | sonnet, high, writes |
| review / verify / audit | `intelligent-delegate:inspector` | sonnet, high, read-only |
| fully-specified fix from findings | `intelligent-delegate:worker` | sonnet, medium, writes |
| transcribe prose into a schema | `intelligent-delegate:mechanical` | haiku (or delete the stage — put the `schema` on the upstream agent) |
| the one call that gates the result | `intelligent-delegate:reviewer` | session model, high |
| contested tie-break, after a split | `intelligent-delegate:judge` | opus, xhigh |

**Generation and verification are different jobs and must not share a tier.** A workflow
that runs every stage at the session tier pays generation prices for clerical work and
clerical prices for the one call that decides whether the output is right.

A `PreToolUse` hook ships with this plugin and **blocks** a `Workflow` whose `agent()`
calls have no `agentType`. If you genuinely need bare opts — `effort: 'max'` is not
expressible in frontmatter — put `// untiered: <reason>` on or just above the call. The
hook fails open on anything it cannot parse, so it is a backstop, not a gate you can lean on.

## Route it in ten seconds

Answer the first question that hits. Stop there. Everything below is backing detail.

1. **Is this ONE target, and would the subagent keep most of what it reads?** →
   **do it inline.** Being able to *name* the files is not enough on its own: twelve
   files you can name is still a fan-out, so count targets before you take this exit.
2. **Is an agent still live on this** — one you spawned with `run_in_background: true`,
   or any agent `ListAgents` shows? → **`SendMessage` it.** Its context is still warm, and
   a resumed agent keeps everything it already read. (A synchronous Agent call that has
   already returned is not live; there is nothing to message, so re-brief a fresh one.)
3. **Name the payoff you are buying** — context protection, tier arbitrage, or
   wall-clock parallelism. Can't name one? → **inline.** (Payoffs are not exclusive, and
   naming one here does not commit you to a cheap tier — see the note under rule 7.)
4. **One target, bounded question, big search, small answer?** → **one Agent call.**
   Omit `model` — *unless* `CLAUDE_CODE_SUBAGENT_MODEL` or a configured default is set, in
   which case omitting silently downgrades; name `reviewer` (read-only) or `builder`
   (writes) to inherit reliably. Both raise effort to `high`, so there is no reliable
   single-call route to *session model at session effort*.
5. **Three or more similar items, or more than one stage per item?** → **Workflow,
   `pipeline()`.** This beats rule 1 whenever they disagree — item count wins over
   "I know which files".
6. **Need a specific effort level or a validated `schema`, and no shipped definition
   fits?** → **Workflow**, even for a single item. That is the only other door.
   **This rule outranks 1 and 3**, the same way 5 does: a single-item job needing a
   validated `schema` is a Workflow even though rule 1 would call it inline and rule 3
   finds no payoff in the list. A `schema` is a correctness mechanism, not a payoff.
7. **Still unsure?** → inline. The floor is higher than it feels.

**Precedence, when two rules fire:** 5 and 6 beat 1 and 3. Within those, answer in order.

**Losing tier arbitrage does not un-justify the delegation.** If you named tier arbitrage
at rule 3 and the safe-downgrade gate later disqualifies the cheap tier, you do **not**
fall back to inline — you delegate at the inherited model — that is what `builder`
is for when the work writes, `reviewer` when it does not — and collect the other payoffs
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

>  **`S` is the term you can actually move, and it tracks tool count — not model tier and
>  not project context.** A 4-tool `reviewer` on Opus has a smaller prefix than an 8-tool
>  `worker` on Sonnet. Restricting `tools:` in a definition is the single biggest token
>  lever available to you, bigger than `omitClaudeMd` and bigger than dropping a tier.

Measured prefixes, the paired A/B behind that claim, and the per-tier table are in
`references/model-selection.md` → "The tool surface is the biggest lever". The two numbers
you need to route *here*: budget `S + C` at **~7–12k** for a scoped definition (4–8 tools)
and **~40k+** for an all-tools agent. Practical break-even: **if D is under ~15k tokens, do
it inline** — an all-tools agent has already spent more than that before it reads anything.

- **High D** — grepping a large tree for one fact, reading a long build log, scanning
  forty files to find the three that matter, driving a browser. Delegate these.
- **Low D** — anything whose output length approaches its input length. Translating a
  paragraph, renaming a symbol, writing one function from a spec you'd have to write
  out anyway. The brief costs as much as the work. Inline.
- **Long-form prose for the user is a bad delegation target.** You pay `R` twice, then
  reproduce it. Unless D is genuinely large, write it yourself.
- **`Explore` and `Plan` omit CLAUDE.md**, so their floor is lower. Route locate-only
  work there rather than to `general-purpose`.
- **Cut `S` first, then `C`.** A narrow `tools:` list is worth roughly 70× what
  `omitClaudeMd` is. Do both, in that order.
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

**All seven tiers work inside a Workflow too.** `agent()` takes `agentType`, so
`agent(prompt, {agentType: 'intelligent-delegate:drafter'})` gets that definition's model
and effort — the same tiers, one parameter over. Use `{model, effort}` directly only when
no shipped definition fits, or when you need `max` effort — and mark that call
`// untiered: <reason>` so the shipped hook passes it.

**Omitting `agentType` is not a cheap tier — it is no tier.** Such an agent inherits the
session model and gets none of the definition's `maxTurns`, tool allowlist,
`omitClaudeMd`, operating rules or return-value contract; the harness logs it as
`workflow-subagent`. `{effort: 'high'}` is not `reviewer`, and `{model: 'haiku'}` is not
`mechanical`. See `references/workflow-patterns.md`, "Addressing a tier".

Inside a Workflow, `pipeline()` is the default — per-item streaming, no barrier. Reach
for `parallel()` only when stage N genuinely needs cross-item context from **all** of
stage N−1 (dedup, rank, early-exit on zero). "I need to flatten first" is not a reason;
do it inside a stage. See `references/workflow-patterns.md`.

**Isolation.** The criterion is not "does this agent write" — it is **can this agent's
inputs change while it runs, no matter who changes them.** Isolate when:

- two or more agents write the **same paths**; or
- any agent runs **git operations** (commit, checkout, stash, branch) — one index and
  one HEAD are shared across the checkout; or
- **you, the orchestrator, will keep editing files the agent is reading.** A read-only
  reviewer is *not* automatically safe: it has nothing to isolate *from itself*, but it
  is still reading a tree you are mutating.

Concurrent writes to **disjoint paths do not conflict** and need no worktree: twelve
agents each editing their own board directory are fine unisolated. Worktrees cost
~200-500ms plus disk *per agent*, so the default is off.

### Coordinating with agents you have already spawned

A subagent reading a file you are simultaneously rewriting will re-read, notice the
mismatch, and spend turns re-verifying — a real cost, paid at that tier's rate, for
nothing. **Measured here:** a `reviewer` audit hit exactly this and spent 26 Bash calls,
most of them `git status` / `cat` / md5 churn establishing which version it was even
looking at.

The protocol, in order of preference:

1. **Freeze, then brief.** Commit first, name the SHA in the brief ("review SKILL.md at
   `abc1234`"), and do not touch those files until the agent returns. Cheapest, and
   needs no worktree.
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

**The Agent tool has no `effort` parameter.** Writing "think hard" or "use high effort"
in the prompt does nothing — you get the default and believe you tuned it. Effort is
reachable exactly two ways:

1. **A shipped agent definition** whose frontmatter sets `effort:` — then pass its name
   as `subagent_type`. The schema accepts `low|medium|high|xhigh|max`, **or an integer**
   (read from the Claude Code 2.1.286 agent-config schema:
   `union([enum(["low","medium","high","xhigh","max"]), int()])`). Note this corrects
   earlier guidance in this file that frontmatter stopped at `xhigh`. Schema acceptance is
   verified; runtime honouring of `max` from frontmatter is not — confirm with one run
   before relying on it.
2. **A Workflow**: `agent(prompt, { effort })` — `low|medium|high|xhigh|max`. Use this when
   effort must vary **per call** rather than per definition; it is not the only route to
   `max`.

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
| session model, `high` | yes, where the model accepts effort | `reviewer` (read-only) or `builder` (can write) — both inherit the model and raise effort. In a Haiku session the `effort` key is dropped, so you get Haiku at its default, not "Haiku at high" |
| session model, `medium` or `low` | **no** | Workflow, or ship a 5-line definition file |
| session model **with Edit/Write** | yes | `builder` — inherits, `high`, has Edit/Write. (`reviewer` inherits but cannot write.) |
| haiku (any effort) | n/a | `mechanical`. **Haiku 4.5 takes no effort setting** — its catalog capability list is `["context_management"]`, with no `"effort"`, where Sonnet and Opus carry `"effort"`/`"xhigh_effort"`/`"max_effort"`. Do not ship `effort:` on a Haiku agent; it reads as a tuned knob and does nothing. |
| sonnet / medium | yes | `worker` |
| sonnet / high | yes | `drafter` (writes) or `inspector` (read-only) — the rung this plugin's own "lower effort before lowering model" advice needs, and did not ship until 0.3.0 |
| opus / xhigh | yes | `judge` |
| anything at `max` | yes | a definition with `effort: max` (schema-legal; runtime unconfirmed), or a Workflow `agent({effort: 'max'})` — the Workflow route is the verified one |

The Agent tool's `model` enum is `haiku|sonnet|opus|fable` — there is **no `inherit`
value to pass**. Omitting `model` only *usually* inherits: it resolves to the **default
subagent model**, which `CLAUDE_CODE_SUBAGENT_MODEL` or a configured default can point
elsewhere. With `CLAUDE_CODE_SUBAGENT_MODEL=haiku`, "omit to inherit" silently hands an
Opus session a Haiku subagent — the exact downgrade this section exists to prevent. The
**reliable** route is a definition whose frontmatter says `model: inherit` literally —
`reviewer` if the work is read-only, `builder` if it must write.

**Lower effort before lowering model.** Effort trades thoroughness against spend
*within* one model — the judgment quality you rely on stays put and the cache stays
warm. Dropping a tier swaps the model and forfeits cache reuse, because caches are
model-scoped.

## Model tier: the no-downgrade predicates

Output-token cost is the number to reason with: **Haiku 1× / Sonnet 2× / Opus 4–5× /
Fable 10×.** (`opus` is an alias for your configured default Opus, which spans two priced
rows — Opus 5.5 at 4×, Opus 5 at 5×. Pin the full id when a budget turns on the difference.)

**The default depends on how many agents you are about to spawn, and this is the correction
0.3.0 exists to make.** Earlier versions of this file said simply "default: inherit the
session model", which is right for *one* delegated call and wrong for a fan-out — it is
how three measured runs cost Opus rates end to end.

- **One agent, and you need session-model judgment** → inherit (`reviewer` / `builder`).
  The cold-start overhead dominates; a tier change saves little and risks the answer.
- **A fan-out, or any multi-stage Workflow** → **start at the pinned-Sonnet rung**
  (`drafter` to generate, `inspector` to verify) and escalate the specific stages where a
  no-downgrade predicate fires. Per-stage escalation is the point of a Workflow; a uniform
  session-model fan-out throws that away and is the single most expensive habit here.

Departing downward from Sonnet to Haiku needs high confidence, which means evaluating the
predicates below rather than waving at them.

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

## The advisor makes every tier price a floor

**Observed 2026-09-30, one session:** every subagent it spawned received an
`advisor_tool` attachment with `available: true` and `model: claude-fable-5-1` — the
**10×** tier. That included `mechanical`, the 1× tier. The advisor *model* is session
configuration, not a harness constant — the model catalog assigns an `advisor_rank` per
model, so another session resolves a different one.

This is session-scoped, not per-agent. The advisor is configured once for the
conversation (`/advisor`, `/advisor <model>`, `/advisor off`, or `--advisor` at launch)
and is then injected into every subagent the session spawns. Consequences:

- **The cost table below is a floor, not a ceiling.** A "1× mechanical" agent that
  consults a Fable advisor once is not a 1× agent for that run.
- **An advisor call silently undoes a downgrade.** The whole point of pinning
  `mechanical` or `worker` is to spend less than the session model; a Fable consult
  inverts that, and nothing in the tier's own definition prevents it.
- **Per-agent suppression is impossible, not merely untested.** Verified in the CLI
  binary: the advisor spec (`advisor_20260301`) is appended to the wire `tools` array
  *after* the client tool list, gated only on whether an advisor model resolved, and it
  executes **server-side** (`server_tool_use` → `advisor_tool_result`). It never passes
  through an agent's allow/deny filter, so there is no local execution point for a
  permission hook to fire on. `disallowedTools: [advisor]` would be a guaranteed no-op.
- **The controls that do work are session-wide:** `/advisor off`, or the environment
  variable `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` for non-interactive and scripted runs.
- **It is not always wrong.** On `judge` or `reviewer` — tiers whose job is correctness
  — a stronger second opinion is the point. On a bulk `mechanical` fan-out it is pure
  cost inversion.

**If you are fanning out many cheap agents and cost predictability matters, ask the user to
turn the advisor off for that session** — `/advisor off` is a slash command only they can
issue, and exporting `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` inside a `Bash` call affects only
that subprocess, not the session that spawns your agents. Until they do, **price the fan-out
at the advisor's tier, not the agent's.** That pricing half is always actionable by you.

### `disallowedTools` is ignored whenever `tools:` is set

A second verified gotcha from the same dig, and it applies to every definition you
write: the frontmatter schema says `disallowedTools` is *"Tools removed from the default
set. **Ignored if `tools` is set.**"* Since `tools:` is an allowlist that **replaces**
the default set, listing both means the deny list does nothing — anything absent from
`tools:` is already gone. This plugin's original five definitions carried
`disallowedTools: [Agent]` alongside a `tools:` allowlist; the line was inert in all
five and has been removed. **Pick one mechanism.** A deny list sitting under an
allowlist reads as a control and is not one.

## Fable

**Never set `model: "fable"` on a subagent** — though note the section above: if an
advisor is configured, your subagents can already *reach* Fable, so this rule is about
not paying Fable rates for every token a subagent emits. The argument is structural:

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

Shipped definitions are namespaced: `intelligent-delegate:mechanical`, and so on.

| type | route here for | never route here for |
|---|---|---|
| `Explore` | locating — which files, where defined, does X exist. Omits CLAUDE.md, cheapest cold start | **review, audit, or absence proofs.** It reads excerpts — an excerpt cannot establish a bug is *not* there |
| `Plan` | step-by-step plans, critical-file lists. No write tools; omits CLAUDE.md | execution |
| `general-purpose` | open-ended multi-step, full tool access | anything a tiered definition covers more precisely |
| `mechanical` (haiku, no effort setting) | homogeneous, specified-by-example edits on small inputs | anything near 150K; anything with a judgment step; **anything needing an MCP tool** — it is the one tier without `ToolSearch`, deliberately |
| `worker` (sonnet/medium) | well-specified implementation with a deterministic check attached | ambiguous specs — it will pick a reading and commit |
| **`drafter` (sonnet/high, writes)** | **the default generation tier.** Producing an artifact from source material you supply: documentation from an evidence file, a runbook, a well-scoped implementation, a pattern applied with per-target adaptation | genuine ambiguity, or a silent-failure blast radius — that is `builder`. Fully specified output — `worker` |
| **`inspector` (sonnet/high, read-only)** | **the default inspection tier.** Ordinary review, verification and audit: checking an artifact against its source, verifying one finding, per-item correctness in a fan-out | negative/universal claims, security-auth-money blast radius, or a verdict carrying many turns — that is `reviewer` |
| `reviewer` (**inherit**/high) | the **escalation** above `inspector`: absence proofs, an invariant the brief does not state, the one verdict that gates the result | ordinary review — `inspector` is half the price whenever the session is above Sonnet. Producing the fix — that is `builder` |
| `builder` (**inherit**/high, **writes**) | the **escalation** above `drafter`: two readings genuinely survive, unsafe-to-downgrade blast radius, failure would be silent | fully specified work — `worker`; ordinary generation — `drafter`. Both cost about half whenever the session model is above Sonnet (in a Sonnet session `drafter` and `builder` are the same thing) |
| `judge` (opus/xhigh) | the call you cannot afford to get wrong, or breaking a tie between two verdicts | routine implementation |

**Routing MCP work.** MCP tools arrive deferred and `ToolSearch` loads them, so a tier must
list `ToolSearch` to reach one — `reviewer`, `worker`, `builder` and `judge` do; `mechanical`
does not. That is necessary, not sufficient: a session can disable `ToolSearch` outright and
the disable is inherited by subagents, in which case no tier reaches MCP and only the user can
change it. Before concluding a tier "cannot do MCP", read the error — a bare
`No such tool available: X` means the name is not registered, while a trailing
"disabled for this session, in subagents as well as here" means the session is the blocker.
`references/model-selection.md` → "Reaching MCP tools from a tier" has the full table.

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
    tool schema on every request — roughly 40k of cold-start prefix against 7–12k for a
    scoped definition. If you reach for `general-purpose` repeatedly, ship a definition
    with a narrow `tools:` list instead.
11. **Editing files an agent you spawned is reading.** It re-reads, sees a mismatch, and
    spends turns establishing which version is real — paid at that agent's tier. Commit
    first and pin the SHA in the brief, or give it a worktree. Read-only does not mean
    collision-free; it means it is not the one causing the collision.
12. **Assuming the tier price is the total.** If an advisor is configured for the
    session, every subagent can reach it — here, Fable at 10×. Price the floor.
13. **Silent caps.** If you bound coverage — top-N, no-retry, sampling — say what was
    dropped. Silent truncation reads as "covered everything" when it didn't.
14. **A uniformly-tiered fan-out.** The most expensive habit in this file, and the one
    with three measurements behind it. If every stage carries the same tier — or no tier —
    you are paying generation prices for clerical work and clerical prices for the call
    that decides whether the output is right. Per-stage tiering is the whole reason to
    reach for a Workflow rather than a loop of Agent calls.
15. **Reading `model: inherit` as "the cheap option".** `reviewer` and `builder` lower
    *effort*, not model. In an Opus session they are Opus. The pinned-Sonnet rung
    (`inspector`, `drafter`) is the actual downgrade.

## References

- `references/model-selection.md` — cost tables, priced fan-outs, the effort × model
  grid, cascade-vs-single-model, and how to set each knob.
- `references/workflow-patterns.md` — barrier decision, the named fan-out shapes, and
  per-stage tiering.
- `references/agent-catalog.md` — every `subagent_type` with its model, effort, tool
  surface, and use/don't-use lines.
