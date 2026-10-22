# Agent catalog

Every value you can pass as `subagent_type`: model, effort, measured speed and cost, and
what it is for — speed, result quality and cost, together. Price ladder, input and output
alike: **Haiku 1x / Sonnet 20x / Opus 40x / Fable 100x.** Haiku is 20x cheaper than Sonnet
on price, about 10x measured (it writes about three times the output tokens), and it is the
cheap model, not the fast one: 1.6x slower than Sonnet at `medium`.

## Contents

- The mechanism (read this first)
- Shipped by this plugin
- Frontmatter keys that cost or save tokens
- Built-ins
- Selection table
- Two cost rules that override the table

## The mechanism (read this first)

The Agent tool takes `prompt`, `subagent_type`, `description`, `model`, `effort`,
`isolation`, `run_in_background`. `model` is exactly `sonnet | opus | haiku | fable`
(`claude-sonnet-5-5`, `claude-opus-5-5`, `claude-haiku-5-5`, `claude-fable-5-1` in 2.1.295);
`effort` takes `low|medium|high|xhigh|max`. The per-call `effort` needs Claude Code v2.1.292
or later.

**Model resolution order** (Claude Code docs, sub-agents and model-config, read 2026-10-22):
(1) the call's `model` parameter; (2) the definition's `model` (`inherit` means the main
conversation's model); (3) `CLAUDE_CODE_SUBAGENT_MODEL`; (4) the main conversation's model.
Since v2.1.251 the env var no longer beats `model: inherit`.
`CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1` (v2.1.257+) makes the env var override every
definition's `model`, every workflow `model` option and the call's `model`, so all tiers
collapse onto one model. `CLAUDE_CODE_EFFORT_LEVEL` beats both frontmatter `effort` and the
call's `effort`; `maxEffortLevel` caps effort. A family alias passed on the call
(`model: "opus"` from an Opus session) resolves to the parent's exact model. A mid-session
`/model` switch also moves what the `inherit` tiers run on. Subagents inherit the session's
extended-thinking on/off (v2.1.198+); there is no per-subagent thinking setting.

Call-site `effort` beats the definition's `effort:` frontmatter, which beats the session's;
`CLAUDE_CODE_EFFORT_LEVEL`, when set, beats all three (resolution order above).
A subagent that names no effort runs at the **session's** effort, not at a default — the
catalog's `default_effort` describes only a session that has not chosen. Every tier here
pins one. Probed 2026-10-09 (`evals/facts-2026-10-09.md`): frontmatter is honoured at
runtime, a call-site `effort` overrides it, an omitted one inherits the session, Haiku 5.5
honours effort. The tool says to set `effort` only when a user or a skill asks; `SKILL.md`
asks. Frontmatter `max` at runtime is not probed, and `max` was not swept.

**Pass `effort: 'high'` on the call before you reach for a different tier.** Change tier on
an escalation predicate, not on a feeling. A tier still earns its place: a definition sets
what a call cannot — the tool allowlist, `maxTurns`, `omitClaudeMd`, the operating rules and
the return-value contract. `SKILL.md` frontmatter `effort:` sets only the invoking turn,
never a subagent (see `model-selection.md`).

Every subagent starts with **cold context** and its final report is **not shown to the
user**, so the caller must relay it. Plugin agents are namespaced:
`intelligent-delegate:worker` when the bare name is ambiguous.

A finished subagent is not necessarily gone. `SendMessage` to a *completed* subagent resumes
it in the background with its full history (also after `TaskStop`); it keeps the tool set it
first ran with and can read its own earlier cache if that cache is still alive (5 minutes by
default) (Claude Code docs, sub-agents, read 2026-10-22). `Explore` and `Plan` cannot be
resumed.

## Shipped by this plugin

| `subagent_type` | model | effort | maxTurns | writes? | price | measured: seconds / cost |
|---|---|---|--:|---|---|---|
| `mechanical` | `haiku` | `low` | 12 | yes | 1x | 18.3 s / $0.0041 |
| `scout` | `haiku` | `low` | 25 | no | 1x | 18.3 s / $0.0041 |
| `worker` | `sonnet` | `medium` | 25 | yes | 20x | 14.0 s / $0.0441 |
| `drafter` | `sonnet` | `high` | 50 | **yes** | 20x | 21.6 s / $0.0586 |
| `inspector` | `sonnet` | `medium` | 50 | no | 20x | 14.0 s / $0.0441 |
| `reviewer` | `inherit` | `high` | 50 | no | session model | 41.7 s / $0.1672 (Opus session) |
| `builder` | `inherit` | `high` | 50 | yes | session model | 41.7 s / $0.1672 (Opus session) |
| `judge` | `opus` | `xhigh` | 50 | no | 40x | 86.2 s / $0.2923 |

The last column: the model x effort cell's mean over four tasks, 2026-10-09 sweep (240 runs,
`opus/xhigh` session; `evals/tier-sweep/RESULTS.md`), on borrowed definitions. `judge`
itself was not measured.

**Defaults, cheap tiers, escalations.** `drafter`, `inspector` and `worker` are where work
starts; `mechanical` and `scout` are Haiku, gated on whether you can tell quickly that a
result is wrong; `reviewer`, `builder` and `judge` are escalations. Three measured fan-outs
ran entirely on Opus partly for want of a "sonnet, but think harder"; see
`workflow-patterns.md` → "The turn cap is the constraint that decides this".

### `mechanical` — haiku / low, with Edit + Write
- **Use when:** the work is fully specified, deterministic, and verifiable without judgment — renaming across files, applying a known pattern, extracting fields, running a checklist. Use it in a fan-out, where parallelism hides the latency: on a 40-record transform it measured a tenth of `worker`'s cost and 1.4x its time, every record right.
- **Do NOT use when:** the task needs a call between defensible alternatives, or you could not tell quickly and cheaply that the result is wrong. A large input is not a disqualifier: Haiku 5.5 has a 1M window. Above 100K prompt tokens it bills 5x its base rate, which is still a quarter of Sonnet's.
- **Pins `low` because an unset effort inherits the session's:** it ran at `xhigh`, 2.5x slower than at `low` (31.8 s against 12.9 s) for the same score.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash. `ToolSearch` is omitted deliberately: an MCP response is unbounded and shaped by a third party, and "convert this by rule" does not describe work against one. `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped (one beside `tools:` would be applied, per the Claude Code docs, but redundant).

### `scout` — haiku / low, read-only
- **Use when:** named facts must come out of a large input — counting or locating entries in a long log, extracting fields from a changelog, finding which of many files mention something — and you can check the answer, or a wrong one is cheap. For a fan-out or a very large corpus. **Not a stage default.**
- **Measured:** on a ten-question log extraction `haiku/low` cost $0.0027 against $0.0356 for `sonnet/medium`, in 10.7 s against 11.9 s, and got 48 of 50 answers where Sonnet and Opus each got 200 of 200. Both misses were one question: the message on the line *after* a named entry; its own search printed both lines and it reported the wrong one. That task ran on `inspector`'s definition with only model and effort overridden; `scout`'s surface is narrower, so the figures describe Haiku at `low` doing this work, not this exact definition.
- **Do NOT use when:** the output is a verdict (review, audit, an absence proof), the task edits files, or you will act on the answer unchecked — use `inspector`. It qualified on cost, not speed.
- **Tools:** Read, Grep, Glob, Bash. `maxTurns` 25 because Haiku made up to 12 requests on that task at `high`. No `ToolSearch`, same mandate reason as `mechanical`. Read-only is a mandate, not a sandbox: Bash can still write.

### `builder` — inherit / high, with Edit + Write (`maxTurns` raised 30 → 50: it reads,
resolves ambiguity, edits, then runs tests/build/linter, and a truncated writer leaves a
partially modified tree with no report of what changed)
- **Use when:** the work must change files AND needs the session model's judgment — a spec
  still ambiguous after you tried to settle it, or a blast radius that makes a downgrade unsafe.
  This is where an escalation predicate sends you when the job still writes code — after
  `drafter` has been ruled out, not instead of considering it.
- **Do NOT use when:** the task is fully specified — `worker` does it for less whenever the
  session model is above Sonnet (roughly half the price on Opus 5.5; in a Sonnet session the
  two differ only by an effort step, since `builder` inherits). On a spec-driven
  implementation `opus/high` took 2.4x the time and 3.4x the cost of `sonnet/high` for the
  same result.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped (one beside `tools:` would be applied, per the Claude Code docs, but redundant).

### `drafter` — sonnet / high, with Edit + Write
- **Use when:** a stage *produces* something substantial from source material you supply —
  documentation from an evidence file, a runbook, a skill, a well-scoped implementation, a
  pattern applied across targets where the brief says how each differs. **This is the default
  generation tier.** Reach for it before `builder` every time; same `high` effort, pinned to Sonnet.
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

### `inspector` — sonnet / medium, read-only
- **Use when:** the verb is review, verify or audit and the job is bounded — checking a
  generated artifact against its source, verifying one claimed finding, a per-item
  correctness pass in a fan-out, edge cases in a contained diff, or a read whose answer you
  will act on. **This is the default inspection tier**, and the right home for a refuter
  panel: refuting one named claim is narrow work, so session-model rates per claim are the
  classic over-escalation.
- **Measured:** on a seeded-defect review it found every defect in every run at `medium`,
  39% faster than at `high` (16.6 s against 27.5 s). That task was **saturated**: it shows
  `medium` is enough for a bounded check, nothing about harder review. For more
  thoroughness pass `effort: 'high'` on the call before reaching for `reviewer` (`opus/high`
  took 3.2x the time and 4.0x the cost of `sonnet/medium` on that task, same result).
- **Do NOT use when:** the deliverable is a negative or universal claim ("nothing else
  writes this field" — absence proofs need exhaustive reading), the blast radius is
  security/auth/money/migrations/concurrency, correctness rests on an unstated invariant,
  or the caller will build many turns on the verdict without re-checking it. Escalate those
  to `reviewer`. Escalate a *split* verdict to `judge`.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch — identical to `reviewer`'s. No Edit or
  Write, which is the practical reason to address it by `agentType` rather than passing
  `{model:'sonnet',effort:'medium'}`: bare opts leave it holding write tools, and a
  "reviewer" that can edit the artifact under review is a worse thing. **Read-only is a
  mandate, not a sandbox:** Bash can still write.
- **It is told to flag its own uncertainty**, so `reviewer` is spent on the two items that need it.

### `worker` — sonnet / medium
- **Use when:** ordinary multi-step implementation or research that needs real comprehension but has a knowable right answer — a scoped feature, tracing a subsystem, tests against a clear spec, **or applying a fix that a review has already specified**.
  For a stage that *generates* a substantial artifact, `drafter` is the default. Pick
  `worker` when the brief genuinely settles the output: on a spec-driven implementation
  `sonnet/medium` matched `sonnet/high`'s score and was 41% faster (18.5 s against 31.6 s).
- **Do NOT use when:** the task is pure mechanical churn in a fan-out (`mechanical` is 20x cheaper on price, about 10x measured, but not faster) or a contested judgment call where being confidently wrong is expensive.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash, WebFetch, WebSearch, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Agent` included — is already unavailable; no `disallowedTools` line is shipped (one beside `tools:` would be applied, per the Claude Code docs, but redundant).

### `reviewer` — inherit / high
- **Use when:** an *escalation* predicate fires on inspection work — a negative or universal claim to establish, a security/auth/money/migration/concurrency blast radius, an invariant the brief does not state, or the single cross-cutting pass that gates the result. `inherit` is deliberate: when review quality has to track the session model, this is the tier that does it. **Ordinary code review, spec-versus-implementation diffs and per-finding adversarial verification go to `inspector` first**, with `effort: 'high'` on the call if it needs more.
- **Do NOT use when:** you want the defect fixed — this tier has no Edit or Write tools; route the fix to `builder` (inherits, can write) — or to `worker` if the fix is fully specified.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Edit`, `Write`, `Agent` — is already unavailable; no `disallowedTools` line is shipped (one beside `tools:` would be applied, per the Claude Code docs, but redundant). Bash can still write, so read-only here is a mandate, not a sandbox. `ToolSearch` is here so this tier can load deferred MCP tools — necessary but not sufficient, see `model-selection.md` → "Reaching MCP tools from a tier".
- **`maxTurns` was the binding constraint, and was raised 20 → 50.** Measured 2026-09-30 (on `claude-opus-5`):
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
- **It is not a cost reduction, or a speed one.** `inherit` means an Opus session gets Opus reviewers, so
  picking this tier over none saves nothing — measured 2026-09-30, a 19-agent fan-out that
  named `reviewer` on all 18 of its review and inventory calls ran 19/19 on `claude-opus-5`
  (the 19th was a `judge` stage, which pins Opus regardless). Fan many of these out and
  price it at the session model, not at a discount. For spend and speed, the levers are the
  pinned tiers — `inspector` at sonnet/medium, `drafter` at sonnet/high, `worker` at
  sonnet/medium, `mechanical` and `scout` at haiku — an explicit `model:` plus `effort` on
  the call, or the tool surface. `inspector` is the direct substitute for this tier and the
  first thing to try. Same applies to `builder`, whose substitute is `drafter`.

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
  an inherited judge in a Sonnet or Haiku session buys only effort. The pin makes `opus / xhigh` reachable regardless of session settings. Wrong only
  in a Fable session, where it downgrades below the caller: adjudicate inline there.
- **Use when:** adjudicating a contested call — two reviewers disagree, an architectural decision is irreversible, the cost of being wrong dominates the price (Opus is 2x Sonnet's).
- **Do NOT use when:** there is a knowable right answer, or when you have not first measured whether `reviewer` at `high` already gets it. Do not fan `judge` out across many items. `opus/xhigh` was the slowest and dearest cell measured, 6.2x the time and 6.6x the cost of `sonnet/medium` for the same score on bounded work.
- **Tools:** Read, Grep, Glob, Bash, ToolSearch. `tools:` is an allowlist, so anything unlisted — `Edit`, `Write`, `Agent` — is already unavailable; no `disallowedTools` line is shipped (one beside `tools:` would be applied, per the Claude Code docs, but redundant). Bash can still write, so read-only here is a mandate, not a sandbox. `ToolSearch` is here so this tier can load deferred MCP tools — necessary but not sufficient, see `model-selection.md` → "Reaching MCP tools from a tier".

## Frontmatter keys that cost or save tokens

Claude Code docs, sub-agents, read 2026-10-22.

- `autoCompactWindow` (100000-1000000, v2.1.296+): compact a long-running subagent earlier.
- `experimental.cacheTtl` (`5m`|`1h`): this subagent's cache lifetime.
- `memory`: adds up to 25KB / 200 lines of MEMORY.md to every run's prompt and force-enables
  Read/Write/Edit even on a read-only `tools:` list. Do not set it on the read-only or cheap
  tiers.
- `skills`: preloads full skill text into every spawn, a direct cost on input per agent.
- `isolation: worktree`: branches from the default branch, not the parent session's HEAD, and
  is cleaned up automatically if the subagent makes no changes. A reviewer in a worktree does
  not see your uncommitted or unmerged work; see `workflow-patterns.md` → "isolation:
  'worktree'".
- Background subagents get a filtered built-in tool set (MCP tools kept; `Agent`,
  `Workflow` and `AskUserQuestion` never available); a definition's `tools:` is intersected
  with it silently.
- `claude plugin validate .claude/agents` catches misspelled frontmatter keys, which are
  otherwise silently ignored.

## Built-ins

### `Explore`
Read-only fan-out search. Reads **excerpts, not whole files**, takes a breadth hint, and
skips CLAUDE.md and the git-status snapshot, which gives it the smallest cold-start prefix.
It runs on the **main conversation's model** (when the session runs Fable on a subscription
or Console, Explore runs on the `opus` alias). It is one-shot: no agent ID, so it cannot be
resumed with `SendMessage` (Claude Code docs, sub-agents, read 2026-10-22).
- **Cost shape:** in an Opus session an Explore call is an Opus call at the session's
  effort: smallest prefix, not cheapest model. For a large locate whose answer you can check,
  `scout` (Haiku) is cheaper; for a read you will act on, `inspector`.
- **Good for:** locating things. Where is X defined, which files touch Y, what exists here.
- **NOT good for:** review, audit, or any verdict. Explore *locates* code; it does not
  judge it, and it never saw the whole file it quoted from. This is the routine misuse —
  an "Explore, and check whether the auth is sound" call returns confident-sounding
  findings drawn from excerpts. Locate with `Explore`, then judge with `inspector` —
  or `reviewer` if an escalation predicate fires.
  Also not for anything that writes, or work needing project conventions (no CLAUDE.md).

### `Plan`
Architect. Returns step-by-step plans and the critical files, with **no write tools**, and
skips CLAUDE.md and the git-status snapshot. It inherits the main conversation's model. Like
`Explore` it is one-shot and cannot be resumed with `SendMessage`.
- **Good for:** turning a vague goal into an ordered plan before any code is touched.
- **NOT good for:** executing the plan, or verifying that existing code matches one.

### `general-purpose`
Full tool access, multi-step, open-ended.
- **Good for:** a task that genuinely needs everything and does not fit a tier.
- **NOT good for:** anything a tiered definition covers. It pins no effort, so it runs at
  the session's, and you lose the tier's tool restrictions, `maxTurns` and rules; effort can
  still be passed on the call. On 2.1.295 it billed 38,112 and 38,131 subagent tokens for a
  one-line echo against 6,824-8,869 for the scoped tiers.

## Selection table

| Task shape | `subagent_type` | Why |
|---|---|---|
| "Where is X handled?" | `Explore` | Locating, not judging; smallest cold-start prefix, on the session model (`scout` is cheaper for a large locate you can check) |
| "Plan the migration" | `Plan` | Architect, no write tools to misfire |
| Rename/reformat across N files | `mechanical` | Deterministic and verifiable; 20x cheaper on price, about 10x measured — **only if the safe-downgrade gate passes**; if "the same edit" could mean adapted-per-target, use `drafter` when the brief says how each target differs and `builder` when working that out is part of the job |
| **Pull named facts from a large log/corpus** | `scout` | Read-only Haiku; only if you can check the answer. Acting on it unchecked: `inspector` |
| Same transform on a very large input | `mechanical`, or `worker` | Fits Haiku's 1M window; past 100K prompt tokens it bills 5x its base rate. `worker` if the reading needs judgment |
| Implement a scoped feature | `worker` | Comprehension with a knowable right answer |
| Trace how a subsystem works | `worker` | Needs whole files, not excerpts |
| **Write docs/a runbook from an evidence file** | `drafter` | Generation from supplied source: sonnet/high with write tools |
| **Draft N artifacts in a fan-out** | `drafter` | The default build stage; `builder` here is the most expensive habit in this plugin |
| Write the fix a reviewer found | `worker` | Findings make it fully specified — cheapest tier that still writes with comprehension |
| Ambiguous spec that still ships code | resolve it first; `builder` if you cannot | Kill one reading — ask, or read one target — and tier by the answer. If two readings still survive, the escalation predicate fires and the job writes |
| **Check an artifact against its source** | `inspector` | Bounded verification; read-only, sonnet/medium |
| **Refute one claimed finding (xN)** | `inspector` | Narrow per-item read — never fan `reviewer` out across items |
| Review a diff for defects | `inspector` first | `effort: 'high'` if it needs more; `reviewer` only on an escalation predicate |
| Prove nothing else writes field X | `reviewer` | A universal claim needs exhaustive reading, not a cheap tier |
| The one pass that gates the result | `reviewer` | Cross-cutting and silent on failure — escalate here, once |
| Two reviewers disagree | `judge` | Adjudication on Opus (2x Sonnet's price), once, not per item |
| Irreversible architectural call | `judge` | Cost of being wrong dominates spend |
| Doesn't fit any of the above | `general-purpose` | Last resort; runs at the session's effort unless you pass one |

## Two cost rules that override the table

1. **Judge cost per completed task, not per request.** A cheaper tier that needs three
   retries and a `reviewer` pass is not cheaper.
2. **A cheaper subagent model forfeits nothing from the orchestrator's cache.** A subagent
   never reads the parent's cache (Claude Code docs, prompt-caching, read 2026-10-22); only
   a fork does, and a fork runs the parent's model. Each subagent writes its own prefix once
   and reads it on its later turns (5-minute TTL by default). What a uniform tier earns is
   sibling sharing within a Workflow stage (same model, effort, agent type, tools, output
   schema and working directory); a per-call `effort` override on one item takes it out of
   the shared prefix. Model-scoped cache loss is real only in the main loop (`/model`,
   `opusplan`, a skill's `model:` frontmatter). Still measure "best model at lower effort"
   before building a cascade; see `model-selection.md`.
