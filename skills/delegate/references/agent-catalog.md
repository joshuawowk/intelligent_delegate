# Agent catalog

Every value you can pass as `subagent_type`, and what it costs. Output-token cost is the
number to reason with: **Haiku 1x / Sonnet 2x / Opus 4-5x / Fable 10x** (the `opus` alias
spans Opus 5.5 at 4x and Opus 5 at 5x).

## The mechanism (read this first)

The Agent tool takes `prompt`, `subagent_type`, `description`, `model`, `isolation`,
`run_in_background`. Its `model` enum is exactly `sonnet | opus | haiku | fable`, and
**there is no `effort` parameter**. Effort is reachable in only two places: the `effort:`
key in an agent definition's frontmatter — the schema accepts `low|medium|high|xhigh|max`
**or an integer** (Claude Code 2.1.286), so `max` is *not* Workflow-only as this repo
previously claimed; schema acceptance is verified, runtime honouring of frontmatter `max` is
not — and the Workflow tool's `agent(prompt, {effort})`, which is the verified route to
`max` and the only way to vary effort per call.

So: *the only way to get a specific effort level out of the Agent tool is to pass the
name of a definition that pins it.* That is what the seven definitions below exist for.
`SKILL.md` frontmatter is **not** a third lever: it does not set a subagent's effort —
only an agent definition does. (See `model-selection.md` for what `effort:` in `SKILL.md` does and does not do.)

Every subagent starts with **cold context** — it cannot see the conversation — and its
final report is **not shown to the user**, so the caller must relay it. Plugin agents are
namespaced: `intelligent-delegate:worker` when the bare name is ambiguous.

## Shipped by this plugin

| `subagent_type` | model | effort | maxTurns | writes? | output cost |
|---|---|---|---|---|---|
| `mechanical` | `haiku` | *(none — Haiku accepts none)* | 12 | yes | 1x |
| `worker` | `sonnet` | `medium` | 25 | yes | 2x |
| `drafter` | `sonnet` | `high` | 50 | **yes** | 2x |
| `inspector` | `sonnet` | `high` | 50 | no | 2x |
| `reviewer` | `inherit` | `high` | 50 | no | session model |
| `builder` | `inherit` | `high` | 50 | yes | session model |
| `judge` | `opus` | `xhigh` | 50 | no | 4-5x |

**Read this table as two columns of defaults and one of escalations.** `drafter` and
`inspector` are the sonnet/high pair added in 0.3.0; they are where generation and
verification should start. `reviewer` and `builder` are the same pair at the session
model — escalations, not defaults. Before 0.3.0 the ladder jumped from sonnet/**medium**
straight to `inherit`, so there was no way to say "sonnet, but think harder" — the advice
this plugin gives in two other places. Three measured fan-outs ran entirely on Opus partly
for that reason; see `workflow-patterns.md` → "Measured".

### `mechanical` — haiku (no effort setting; Haiku accepts none)
- **Use when:** the work is fully specified, deterministic, and verifiable without judgment — renaming across files, applying a known pattern, extracting fields, running a checklist.
- **Do NOT use when:** the task needs a call between defensible alternatives, **or reads a lot** — Haiku's context is 200K, a hard ceiling that no amount of "but it's mechanical" overrides.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash (+ `ToolSearch` on `builder`, for deferred MCP tools; `mechanical` omits it deliberately — MCP payloads are unbounded and it has a 200K wall). `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped or would be honoured.

### `builder` — inherit / high, with Edit + Write (`maxTurns` raised 30 → 50: it reads,
resolves ambiguity, edits, then runs tests/build/linter, and a truncated writer leaves a
partially modified tree with no report of what changed)
- **Use when:** the work must change files AND needs the session model's judgment — an
  ambiguous spec, per-target adaptation, or a blast radius that makes a downgrade unsafe.
  This is where an escalation predicate sends you when the job still writes code — after
  `drafter` has been ruled out, not instead of considering it.
- **Do NOT use when:** the task is fully specified — `worker` does it for less whenever the
  session model is above Sonnet (roughly half on Opus 5.5, 40% of it on Opus 5; in a Sonnet
  session the two differ only by an effort step, since `builder` inherits).
- **Tools:** Read, Grep, Glob, Edit, Write, Bash (+ `ToolSearch` on `builder`, for deferred MCP tools; `mechanical` omits it deliberately — MCP payloads are unbounded and it has a 200K wall). `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped or would be honoured.

### `drafter` — sonnet / high, with Edit + Write
- **Use when:** a stage *produces* something substantial from source material you supply —
  documentation from an evidence file, a runbook, a skill, a well-scoped implementation, a
  pattern applied across targets with per-target adaptation. **This is the default
  generation tier.** Reach for it before `builder` every time; it is the same `high`
  effort, pinned to Sonnet.
- **Do NOT use when:** two readings of the brief genuinely survive, correctness rests on an
  invariant the brief does not state, the blast radius is security/auth/money/migrations/
  concurrency, or a failure would be silent to you — those are `builder`. Also not when the
  brief fully specifies the output: `worker` does that for less, and `mechanical` does
  specified-by-example edits for less still.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash, ToolSearch. `tools:` is an allowlist, so
  anything unlisted — `Agent` included — is already unavailable.
- **Its mandate is anti-rot**, which matters when the artifact is documentation: write the
  command that re-derives a volatile value rather than the value, and name gaps in the
  source instead of filling them plausibly.

### `inspector` — sonnet / high, read-only
- **Use when:** the verb is review, verify or audit and the job is bounded — checking a
  generated artifact against its source, verifying one claimed finding, a per-item
  correctness pass in a fan-out, edge cases in a contained diff. **This is the default
  inspection tier**, and it is the right home for a refuter panel: refuting one named
  claim is narrow work, so paying session-model rates per claim is the classic
  over-escalation.
- **Do NOT use when:** the deliverable is a negative or universal claim ("nothing else
  writes this field" — absence proofs need exhaustive reading), the blast radius is
  security/auth/money/migrations/concurrency, correctness rests on an unstated invariant,
  or the caller will build many turns on the verdict without re-checking it. Escalate those
  to `reviewer`. Escalate a *split* verdict to `judge`.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch. No Edit or Write — which is the practical
  reason to address it by `agentType` rather than passing `{model:'sonnet',effort:'high'}`:
  bare opts leave it holding write tools, and a "reviewer" that can edit the artifact under
  review is a different and worse thing.
- **It is told to flag its own uncertainty**, so a caller can spend `reviewer` on the two
  items that need it instead of the whole stage.

### `worker` — sonnet / medium
- **Use when:** ordinary multi-step implementation or research that needs real comprehension but has a knowable right answer — a scoped feature, tracing a subsystem, tests against a clear spec, **or applying a fix that a review has already specified**.
  As of 0.3.0 this is no longer "the default shipped tier": for a stage that *generates* a
  substantial artifact, `drafter` is the default and runs the same model a step higher. Pick
  `worker` when the brief genuinely settles the output, which is also when it is about 26%
  cheaper than `drafter`.
- **Do NOT use when:** the task is pure mechanical churn (pay 1x instead) or a contested judgment call where being confidently wrong is expensive.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash, WebFetch, WebSearch, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped or would be honoured.

### `reviewer` — inherit / high (high only where the inherited model accepts effort)
- **Use when:** an *escalation* predicate fires on inspection work — a negative or universal claim to establish, a security/auth/money/migration/concurrency blast radius, an invariant the brief does not state, or the single cross-cutting pass that gates the result. `inherit` is deliberate: when review quality has to track the session model, this is the tier that does it. **Ordinary code review, spec-versus-implementation diffs and per-finding adversarial verification go to `inspector` first** — same effort, pinned to Sonnet. Routing all review here is how three measured fan-outs cost Opus rates.
- **Do NOT use when:** you want the defect fixed — this tier has no Edit or Write tools; route the fix to `builder` (inherits, can write) — or to `worker` if the fix is fully specified.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Edit`, `Write`, `Agent` — is already unavailable; no `disallowedTools` line is shipped or would be honoured. Bash can still write, so read-only here is a mandate, not a sandbox. `ToolSearch` is here so this tier can load deferred MCP tools — necessary but not sufficient, see `model-selection.md` → "Reaching MCP tools from a tier".
- **`maxTurns` was the binding constraint, and was raised 20 → 50.** Measured 2026-09-30:
  under the old cap of 20, 6 of 7 reviewers and 4 of 4 inventory agents in a repo audit
  landed on **exactly 20 calls** — guillotined mid-task. Only the one that finished at 17
  produced findings that reached the next stage. Then measured uncapped on the same
  workload — those agents were **untiered** (`workflow-subagent`: no cap, no allowlist, none
  of this tier's operating rules), so read the distribution as the closest available proxy
  for this tier's demand rather than a measurement of it: ten broad reviewers used **15, 18,
  18, 20, 22, 29, 35, 36, 41, 45** turns, sixty narrow per-finding verifiers **4–17**. 50 covers the broad
  distribution with headroom and is invisible to the narrow one, since a ceiling costs
  nothing for work that finishes early. This is the same correction `judge` got twice, at
  15 → 25 and again at 25 → 50 — a turn budget has to fund the mandate the tier's prose
  sets, and "follow the call
  chain, check the callers" is the most read-heavy mandate here. Before the fix `reviewer`
  had the *tightest* non-mechanical cap in the plugin, below `worker` (25) and
  `builder` (30), which was backwards. The case that fixed the number: the reviewer
  auditing credential exposure needed **41 turns** to return a 25,898-character report
  finding four secrets an earlier pass missed. Caps of 25, 30 and 35 would all have
  destroyed it; 50 clears it by nine turns.
- **It is not a cost reduction.** `inherit` means an Opus session gets Opus reviewers, so
  picking this tier over none saves nothing — measured 2026-09-30, a 19-agent fan-out that
  named `reviewer` on all 18 of its review and inventory calls ran 19/19 on `claude-opus-5`
  (the 19th was a `judge` stage, which pins Opus regardless). Fan many of these out and
  price it at the session model, not at a discount. For spend, the levers are the pinned
  tiers — `inspector` and `drafter` at sonnet/high, `worker` at sonnet/medium, `mechanical`
  at haiku — an explicit `model:` in a Workflow `agent()` call, or the tool surface.
  `inspector` is the direct substitute for this tier and the first thing to try.
  Same applies to `builder`, whose substitute is `drafter`.

### `judge` — opus / xhigh
- **`maxTurns` raised 25 → 50, on weaker evidence than `reviewer`'s.** This tier has hit
  its cap twice — at 15 (raised to 25) and again at exactly 25, truncated mid-adjudication.
  The one uncapped observation of the same consolidation work used **34** turns; n=1, so 50
  is a deliberately generous ceiling rather than a fitted number. Justified because a
  ceiling is free for adjudications that finish early, because this tier is never fanned
  out (one agent's runaway, not sixty), and because a cap below `reviewer`'s 50 would assert
  that adjudication investigates less than review — backwards for the tier told to read
  primary sources and argue the losing side first.
- **Why it pins while `reviewer`/`builder` inherit:** defect-finding is effort-bound;
  adjudication is capability-bound. Escalating must buy capability the caller lacks, and
  an inherited judge in a Sonnet or Haiku session buys only effort — on Haiku, not even
  that. The pin makes `opus / xhigh` reachable regardless of session settings. Wrong only
  in a Fable session, where it downgrades below the caller: adjudicate inline there.
- **Use when:** adjudicating a contested call — two reviewers disagree, an architectural decision is irreversible, the cost of being wrong dominates the 4-5x token cost.
- **Do NOT use when:** there is a knowable right answer, or when you have not first measured whether `reviewer` at `high` already gets it. Do not fan `judge` out across many items.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Edit`, `Write`, `Agent` — is already unavailable; no `disallowedTools` line is shipped or would be honoured. Bash can still write, so read-only here is a mandate, not a sandbox. `ToolSearch` is here so this tier can load deferred MCP tools — necessary but not sufficient, see `model-selection.md` → "Reaching MCP tools from a tier".

## Built-ins

### `Explore`
Read-only fan-out search. Reads **excerpts, not whole files**, takes a breadth hint, and
**omits CLAUDE.md**, which makes its cold start cheaper than a custom definition's.
- **Good for:** locating things. Where is X defined, which files touch Y, what exists here.
- **NOT good for:** review, audit, or any verdict. Explore *locates* code; it does not
  judge it, and it never saw the whole file it quoted from. This is the routine misuse —
  an "Explore, and check whether the auth is sound" call returns confident-sounding
  findings drawn from excerpts. Locate with `Explore`, then judge with `inspector` —
  or `reviewer` if an escalation predicate fires.
  Also not for anything that writes, and not for work needing project conventions,
  since it does not get CLAUDE.md.

### `Plan`
Architect. Returns step-by-step plans and the critical files, with **no write tools** and
no CLAUDE.md.
- **Good for:** turning a vague goal into an ordered plan before any code is touched.
- **NOT good for:** executing the plan, or verifying that existing code matches one.

### `general-purpose`
Full tool access, multi-step, open-ended.
- **Good for:** a task that genuinely needs everything and does not fit a tier.
- **NOT good for:** anything a tiered definition covers — it pins no effort, so you get
  the default, and you lose the tier's tool restrictions along with it. Preferring it by
  reflex is how the whole effort mechanism gets bypassed.

## Selection table

| Task shape | `subagent_type` | Why |
|---|---|---|
| "Where is X handled?" | `Explore` | Locating, not judging; cheapest cold start |
| "Plan the migration" | `Plan` | Architect, no write tools to misfire |
| Rename/reformat across N files | `mechanical` | Deterministic and verifiable; 1x — **only if the safe-downgrade gate passes**; if "the same edit" could mean adapted-per-target, use `drafter` when the brief says how each target differs and `builder` when working that out is part of the job |
| Same, but 400K of input | `worker` | Haiku's 200K context is a hard wall |
| Implement a scoped feature | `worker` | Comprehension with a knowable right answer |
| Trace how a subsystem works | `worker` | Needs whole files, not excerpts |
| **Write docs/a runbook from an evidence file** | `drafter` | Generation from supplied source: sonnet/high with write tools |
| **Draft N artifacts in a fan-out** | `drafter` | The default build stage; `builder` here is the most expensive habit in this plugin |
| Write the fix a reviewer found | `worker` | Findings make it fully specified — cheapest tier that still writes with comprehension |
| Ambiguous spec that still ships code | `builder` | Safe-downgrade gate fails but the job writes |
| **Check an artifact against its source** | `inspector` | Bounded verification; read-only, sonnet/high |
| **Refute one claimed finding (xN)** | `inspector` | Narrow per-item read — never fan `reviewer` out across items |
| Review a diff for defects | `inspector` first | Escalate to `reviewer` only if an escalation predicate fires |
| Prove nothing else writes field X | `reviewer` | A universal claim needs exhaustive reading, not a cheap tier |
| The one pass that gates the result | `reviewer` | Cross-cutting and silent on failure — escalate here, once |
| Two reviewers disagree | `judge` | Adjudication at 4-5x, once, not per item |
| Irreversible architectural call | `judge` | Cost of being wrong dominates spend |
| Doesn't fit any of the above | `general-purpose` | Last resort; no effort pinned |

## Two cost rules that override the table

1. **Judge cost per completed task, not per request.** A cheaper tier that needs three
   retries and a `reviewer` pass is not cheaper.
2. **Caches are model-scoped.** A cascade across models forfeits cache reuse between
   them — measure "best model at lower effort" before building one.
