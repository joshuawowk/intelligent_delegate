# Workflow patterns: shape, then tier

Routing already concluded "this needs a Workflow." Two decisions remain: which
**shape**, and what **tier** each stage runs at. The second one is where the money is.

## Addressing a tier: `agentType`, not bare opts

`agent()` opts can set a stage's `model` and `effort` (plus `schema`, `label`, `phase`,
`isolation`). What they **cannot** set is everything else a tier carries: `tools`,
`maxTurns`, `omitClaudeMd`, the operating rules and the return-value contract all live in
the definition's frontmatter and body, reachable **only** through `agentType`.

So an `agent()` call with no `agentType` is not a cheap tier. It is an untiered agent that
**inherits the session model** and gets the harness default for everything a definition
would otherwise scope. The harness logs it as `agentType: "workflow-subagent"`.

**As of 0.3.0 this is enforced, not advised.** A `PreToolUse` hook
(`hooks/tier_check.py`) lexes the script you pass to `Workflow` and denies the call if any
`agent()` has no `agentType`, naming the line numbers. It lexes rather than greps, so
`agent()` discussed inside a prompt string — which these docs do constantly — is not a
call site. It fails open on anything it cannot parse. Waive a call with
`// untiered: <reason>` on or just above it.

The hook exists because the advice did not work. It was written correctly, in this file,
and three measured fan-outs ignored it anyway — see "Measured" below. Guidance that has
failed three times needs an exit code, not a fourth printing.

| You want | Write | Bare-opts form, and what it silently loses |
|---|---|---|
| mechanical | `{agentType: 'intelligent-delegate:mechanical'}` | `{model: 'haiku'}` buys Haiku pricing but **not** `omitClaudeMd`, the 6-tool allowlist or `maxTurns: 12` — and tool surface is the lever that measured **4.4× the input for an identical answer** (`model-selection.md`, "The tool surface is the biggest lever"). No `effort` either way; Haiku accepts none. |
| worker | `{agentType: 'intelligent-delegate:worker'}` | `{model: 'sonnet', effort: 'medium'}` — loses `maxTurns: 25` and the operating rules |
| **drafter** (default to generate) | `{agentType: 'intelligent-delegate:drafter'}` | `{model: 'sonnet', effort: 'high'}` gets the price but not the Edit/Write surface, `maxTurns: 50`, or the rules about not upgrading a snapshot into a standing fact |
| **inspector** (default to verify) | `{agentType: 'intelligent-delegate:inspector'}` | `{model: 'sonnet', effort: 'high'}` gets the price but **not** the read-only tool surface — so your "reviewer" can edit the thing it is reviewing — nor `maxTurns: 50`, nor the return-value contract |
| reviewer (escalation) | `{agentType: 'intelligent-delegate:reviewer'}` | `{effort: 'high'}` **does not give you `reviewer`.** No `maxTurns`, no read-only tool surface, no return-value contract — and it inherits the session model, so it is not a downgrade at all. Note this tier is the *escalation* above `inspector`, not the default |
| builder (escalation) | `{agentType: 'intelligent-delegate:builder'}` | none worth using: the point of this tier is its Edit/Write surface, and `tools` is not settable through opts. The *default* writing tier is `drafter` |
| judge | `{agentType: 'intelligent-delegate:judge'}` | `{model: 'opus', effort: 'xhigh'}` — reach for opts here only when you need `effort: 'max'`, which frontmatter cannot express |

Pass bare `{model, effort}` deliberately — for `max` effort, when no shipped definition
fits, **or when the stage needs more turns than the tier budgets** — never as shorthand for
a tier.

### The turn cap is the constraint that decides this

`agentType` brings `maxTurns` with it, and that cap is enforced mid-task: the harness ends
the turn, so an agent cannot "just wrap up" — including by emitting its `schema` call. A
capped stage returns nothing and everything downstream of it silently gets no work.

**Measured, 2026-09-30 — this is what killed a 19-agent run.** Every agent used
`agentType: 'intelligent-delegate:reviewer'` (cap **20 at the time**, since raised to 50
on this evidence) or `:judge` (cap **25 at the time**, since also raised to 50).
Distinct API calls per agent:

| agent | calls | cap | |
|---|--:|--:|---|
| 4 of 4 Inventory | 20 | 20 | at cap |
| 6 of 7 Review | 20 | 20 | at cap |
| `review:mcp-correctness` | 17 | 20 | finished |
| Consolidate (judge) | 25 | 25 | at cap |

**11 of 19 agents landed exactly on their cap.** Only the one reviewer that came in under
it produced findings that reached the Verify stage — the other six dimensions contributed
nothing, and the run then died on the judge with
`agent({schema}): subagent completed without calling StructuredOutput`. That error is the
*symptom of the cap*, not an agent forgetting: agents in that same run called
`StructuredOutput` 8 times successfully — the capped ones never got a turn to.

The follow-up run left `agentType` off entirely, which removed the tier cap and so
measured the **natural demand** for the same work. Ten broad reviewers used 15, 18, 18,
20, 22, 29, 35, 36, 41 and 45 turns — **seven of ten at or over 20.** Sixty narrow
per-finding verifiers used 4–17, and ten schema-transcription stages used exactly 1 each.
`reviewer` is now `maxTurns: 50` because of those numbers.

So before routing a stage to a tier, ask what it costs in **turns**, not just tokens:

- **Turn demand tracks breadth, not difficulty.** On identical subject matter: 1 turn to
  transcribe into a schema, 4–17 to verify one finding, 15–45 to review a whole dimension.
  Size the cap to the broadest stage that will use the tier.
- `maxTurns` is frontmatter-only; no `agent()` opt raises it for one stage. If a stage needs
  more than its tier budgets, your choices are bare opts (losing the tier's other
  guarantees) or raising the cap in the definition.
- **A ceiling is free for work that finishes early.** Raising a cap does not pre-allocate
  anything — the 60 verifiers above would be unaffected by any cap over 17. So size for the
  worst legitimate case; the cost of a generous ceiling is only how long a genuinely stuck
  agent runs before dying.
- Whatever cap applies, **leave a turn for the return**. A schema stage that spends its
  last turn reading one more file fails the stage outright.
- **Diagnostic:** when a fan-out underdelivers, count distinct `message.id`s per agent and
  compare to the tier's cap *before* suspecting the model or the prompt. An exact landing
  on the cap is never a coincidence.

**Measured, 2026-09-30.** An 81-agent audit fan-out passed only `{label, phase, schema,
effort}` at all four call sites. Every agent logged `agentType: "workflow-subagent"` and
ran `claude-opus-5`: the tiers were never engaged, including a 10-agent stage whose prompt
was pure schema transcription. A 19-agent run in the same session passed
`agentType: 'intelligent-delegate:reviewer'` on all 18 of its review and inventory calls —
correct usage; the 19th was a `judge` stage, which pins Opus anyway — and *also* ran
all-Opus, because `reviewer` inherits. Both paths cost Opus rates: **$120–145** for 100 agents
at standard cache rates (0.1× input for cache reads, 1.25–2× for writes depending on TTL),
against ~$48–58 for the same tokens on Sonnet. Derivation: 1.26M output, 75.8M cache-read
and 5.9M cache-write tokens over 1,052 API calls. That is **~4× the 40K-input/5K-output
per-agent assumption** used in `model-selection.md`, which is why its table would price 100
Opus agents near $33 — these agents read far more. Substitute your own per-agent token
estimate; the figure is linear in it.

**Measured again, 2026-10-08 — the same defect, in a session with this skill loaded.**
Four scripts, 13 `agent()` calls, 100% `claude-opus-5`. Eight calls passed
`{label, phase}` only; the other five passed `agentType: '…:reviewer'`, which inherits. So
both 2026-09-30 failure modes recurred simultaneously, eleven days after both were written
up here. Two conclusions, and 0.3.0 acts on both:

1. **The prose was not the fix.** Hence the `PreToolUse` hook above. It was tested against
   these four scripts and denies all four, at the right line numbers.
2. **One of the two was not a usage error at all.** The job was writing eighteen
   documentation skills from a verified facts file — textbook `sonnet`/high generation. But
   the ladder went `worker` (sonnet/**medium**) straight to `builder`/`reviewer`
   (`model: inherit`). There was **no `sonnet`/high rung**, so "more than `worker`
   deserves" had only one destination: the session model. The plugin was recommending
   "lower effort before lowering model" and `sonnet`/medium → `sonnet`/high while shipping
   a tier set that could not express it. `drafter` and `inspector` close that gap.

Output-token cost ratio: haiku 1x, sonnet 2x, opus 4-5x, fable 10x. `effort` is reachable
inside a Workflow script and in an agent definition's frontmatter — the `Agent` tool has
no `effort` parameter. That is why per-stage tiering is a Workflow capability.

## pipeline() vs parallel(): the barrier decision

`pipeline(items, ...stages)` streams per item — item A can be in stage 3 while item B
is still in stage 1. Wall-clock is the slowest single-item *chain*. This is the default.

`parallel(thunks)` is a **barrier**: nothing downstream starts until every thunk settles.

A barrier is genuinely justified in exactly three cases:

1. **Cross-item dedup or merge** before expensive downstream work — you cannot dedupe
   finding #3 against findings you have not collected yet.
2. **Early exit on the aggregate** — "zero findings total, so skip verification entirely."
3. **Stage N's prompt references the other items** — comparison, ranking, "pick the best of these."

Four rationalizations that do **not** justify one:

1. "I need to flatten/map/filter first." Do it inside a stage:
   `pipeline(items, stageA, r => transform([r]).flat(), stageB)`.
2. "The stages are conceptually separate." That is what `pipeline()` models.
   Separate ≠ synchronized.
3. "It's cleaner code." Barrier latency is real spend. If the slowest finder takes 3x
   the fastest, the fast ones idle for 2/3 of the stage.
4. "There are only a few items." One slow outlier still gates everything.

**Smell test:** `const a = await parallel(...); const b = transform(a); await parallel(b.map(...))`
— if `transform` has no cross-item dependency, that barrier is unearned.

## The named shapes

- **Adversarial verify** — N independent skeptics per finding, each prompted to *refute*,
  defaulting to refuted when uncertain. Kill on majority refutation. For: plausible-but-wrong
  findings that survive a single confirm-shaped check.
- **Perspective-diverse verify** — same fan-out, but each verifier gets a distinct lens
  (correctness / security / perf / does-it-reproduce). For: findings that can fail in more
  than one way, where redundancy would miss the mode nobody looked for.
- **Judge panel** — generate N attempts from different angles (MVP-first, risk-first,
  user-first), score with parallel *scorers* (`reviewer` tier — not the `judge` tier, which
  is costed on never being fanned out), synthesize from the winner while grafting the
  runners-up. For: wide solution spaces, where one-attempt-iterated locks in early.
- **Loop-until-dry** — keep spawning finders until K consecutive rounds surface nothing
  new; dedupe against everything *seen*, not everything *confirmed*, or rejected findings
  reappear forever. For: unknown-size discovery, where `while (count < N)` misses the tail.
- **Multi-modal sweep** — parallel agents each searching a different way (by container,
  by content, by entity, by time), blind to one another. For: when no single search angle
  reaches everything.
- **Completeness critic** — one final agent asking "what is missing: a modality not run,
  a claim unverified, a source unread?" Its output is the next round's work-list.

## Per-stage tiering

**Generation and verification are not the same job and should not share a tier.**
Generation is open-ended and repays effort; verification against a concrete artifact is
narrower and often repays a *different* model entirely. A workflow that runs every stage
at the session tier is paying generation prices for clerical work and clerical prices for
the one call that decides whether the output is right.

| Shape | Drop to mechanical | Default rung (pinned sonnet) | Escalate (inherits / opus) |
|---|---|---|---|
| Build → review → fix | — | build at `…:drafter`, review at `…:inspector`, fix at `…:worker` | the one cross-cutting pass at `…:reviewer` |
| Adversarial verify | — | refuters at `…:inspector` | `…:judge` tie-break when the vote splits |
| Perspective-diverse verify | — | each lens at `…:inspector` | the lens that gates a release, at `…:reviewer` |
| Judge panel | — | the N generators at `…:drafter` | the final synthesis at `…:judge` |
| Loop-until-dry | per-round severity/triage classification | the finders at `…:inspector` | final confirm pass only |
| Multi-modal sweep | — | each arm (`agentType: 'Explore'`), then the merge | rarely |
| Completeness critic | — | — | the critic itself, `agentType: '…:judge'` |

**The middle column is the one that changed in 0.3.0.** It used to read "`worker` pins
sonnet; `reviewer` inherits", which meant every judgment-shaped mid-tier stage resolved to
the session model. `inspector` and `drafter` pin sonnet at **high** effort, so the default
rung is now a real rung rather than a pointer back at the top of the ladder.

Cells name `agentType`, not bare `{effort}`, for the reason at the top of this file: bare
opts give you the model and effort but none of the tier's cap, tool surface or
return-value contract. A refuter built from `{effort: 'high'}` alone is an untiered agent
with write tools it should not have and no instruction that its final message is the
deliverable — which is exactly the vanished-stage failure described below. It is also what
the shipped hook denies.

Before dropping a stage to mechanical, ask whether it needs an agent at all: dedupe and
merge are plain JS, and structured extraction is a `schema` on the upstream agent. The
cheapest mechanical stage is no agent. Three rules override the table:
- **Haiku's 200K context is hard.** Never route a stage that reads a whole diff, a long
  transcript, or a broad repo excerpt to haiku, however mechanical it looks. An adversarial
  refuter reading a large generation output is not a haiku candidate.
- **Caches are model-scoped.** Adjacent stages sharing a large prompt should prefer *same
  model, different effort* (`sonnet`/medium → `sonnet`/high) over model-hopping. Drop the
  model only when the stage's input is small and independent.
- **Judge cost per completed task, not per request.** "Haiku is 5x cheaper than opus" is a
  rationalization if that stage needs two retries. Measure best-model-at-lower-effort
  before building a cascade.

One stage shape is always mechanical: **transcribing an upstream agent's prose into a
schema.** "Convert this report into structured findings; do not add, remove or invent"
is fully specified and verifiable without judgment. Route it to
`agentType: 'intelligent-delegate:mechanical'` — but keep the retry from the next section,
because a schema stage is exactly where a cheap model fails by not calling
StructuredOutput at all. Better still, check whether the stage is needed: a `schema` on
the upstream agent removes it entirely.

## `schema` injects a tool the allowlist does not list

Passing `schema` to `agent()` makes the stage return through the `StructuredOutput` tool,
and **that tool is not subject to the definition's `tools:` allowlist.** Verified from
transcripts: eight agents running `agentType: 'intelligent-delegate:reviewer'`, whose
allowlist is exactly `[Read, Grep, Glob, Bash]`, each called `StructuredOutput` successfully.
So you never need to add it to a `tools:` list, and a read-only tier can still satisfy a
schema. The failure mode is the opposite one — see the turn cap above: a capped agent never
reaches its schema call, and the stage fails with
`subagent completed without calling StructuredOutput`.

## The return value is the deliverable

A workflow harvests each agent's **final message**. Not files it wrote, not what it logged.
An agent that writes its report to disk and returns "report is durable at 2716 words" has
returned nothing the pipeline can use.

Two things make that shape likely, and they compound:

- **An untiered agent has no return-value contract.** Every shipped definition closes with
  "Your final message IS the return value — the caller reads it programmatically and the
  user never sees it." An `agent()` call without `agentType` never sees that line.
- **An injected advisor tells agents to persist first, then hand off.** When the session has
  an advisor configured, every subagent inherits it (`model-selection.md`, "An advisor
  re-prices every row") together with instructions to make the deliverable durable *before*
  consulting. Followed literally, that produces precisely the write-then-announce shape.

So **never silently drop a short return.** This guard destroys a completed stage:

```js
if (!report || String(report).trim().length < 200) return null   // work vanishes, unlogged
```

Log what you discarded and retry once with the contract restated:

```js
if (!report || String(report).trim().length < MIN) {
  log(`${d.key}: return too short (${String(report || '').length} ch): ${String(report).slice(0, 200)}`)
  report = await agent(
    `${d.prompt}\n\nYour FINAL MESSAGE is the deliverable. Do not write it to a file, and do not end on a status line — emit the full report as your reply.`,
    {agentType: 'intelligent-delegate:reviewer', label: `review:${d.key}:retry`, phase: 'Review'})
}
```

**Observed near-miss, 2026-09-30.** In the 81-agent run above, the reviewer covering
secrets and credential exposure emitted "The report is durable at 2716 words. Let me have
the advisor review before finalizing." — 86 characters, under a 200-character guard. Its
nine sibling reviewers returned 21k–38k characters each. It recovered — the run finished
and it returned a 25,898-character report at turn 41 — so this was a near-miss, not a loss.
But had its turn ended on that line, the only security review in the fan-out would have
been dropped on a length check, with no log line and no retry. And that report is the one
that found four independent secrets an earlier pass had missed. The guard is the
single-point-of-failure here, not the agent.

## Budget-aware scaling

`budget` is `{total: number|null, spent(): number, remaining(): number}`. `total` is null
when the user set no "+500k"-style target, and then `remaining()` is `Infinity`.

**The trap:** an unguarded `while (budget.remaining() > 50_000)` never terminates on its
own when no target was set — its only stop is the 1000-agent lifetime cap. Always guard on
`budget.total` first:

```js
while (budget.total && budget.remaining() > 50_000) { /* ... */ }
```

Static scaling: `const FLEET = budget.total ? Math.floor(budget.total / 100_000) : 5`.
The budget is a hard ceiling shared with the main loop: once `spent()` reaches `total`,
`agent()` throws.

## isolation: 'worktree'

Real cost: ~200-500ms plus disk setup **per agent**, on top of the token spend. The only
condition that justifies it is that a stage's **inputs can change while it runs** — two
stages writing the **same paths**, any stage running **git operations** (commit, checkout,
stash), which share one index and HEAD, or **the orchestrator editing files a stage is
reading**. That last case is the one people miss: a read-only verify stage is not safe
merely because it does not write, if the caller is rewriting the tree underneath it.
Concurrent writes to **disjoint paths are safe unisolated**: twelve agents each editing
their own directory need no worktree. Every verify,
judge, critic, and search stage is read-only and needs no worktree **provided the tree is
stable while it runs** — if you will keep editing, either freeze and pin a SHA in the
brief or give it one after all. The worktree is auto-removed if unchanged,
so an isolated read-only agent paid the setup for nothing.

## The concurrency cap

`min(16, CPUs - 2)` agents run at once per workflow; the rest queue. On an 8-core box that
is 6, so a 40-item fan-out is ~7 waves, not one. Passing 200 items is still fine (4096 is
the per-call limit) — it just takes 34 waves. Two consequences:

- A `parallel()` barrier over a large fan-out waits for the slowest item of the *last*
  wave, so it costs wall-clock on top of tokens. Another reason `pipeline()` is the default.
- Widening a fan-out past the cap buys coverage, not speed. If you bound coverage instead
  (top-N, sampling, no-retry), `log()` what was dropped — silent truncation reads as
  "covered everything."

## Sketch: per-stage tiering in one pipeline

```js
export const meta = {
  name: 'tiered-review',
  description: 'Find, verify, and synthesize findings with per-stage tiering',
  phases: [
    // `model` on a phase entry documents that phase's override — add it whenever a
    // stage passes opts.model, so the progress display matches what actually runs.
    // Each phase names the model its tier pins, so the progress display matches what runs.
    {title: 'Find', detail: 'one finder per target file', model: 'sonnet'},      // worker
    {title: 'Triage', detail: 'cheap severity classification', model: 'haiku'},  // mechanical
    {title: 'Verify', detail: 'adversarial refutation', model: 'sonnet'},        // inspector
  ],
}

const FINDINGS = {type: 'object', required: ['findings'],
  properties: {findings: {type: 'array', items: {type: 'string'}}}}
const TRIAGED = {type: 'object', required: ['triaged'],
  properties: {triaged: {type: 'array', items: {type: 'object',
    required: ['claim', 'severity'],
    properties: {claim: {type: 'string'}, severity: {type: 'string'}}}}}}
const VERDICT = {type: 'object', required: ['refuted'],
  properties: {refuted: {type: 'boolean'}, why: {type: 'string'}}}

const targets = args && args.length ? args : ['src/auth.js', 'src/session.js']

const reviewed = await pipeline(
  targets,
  // Generation: reads the whole file, open-ended. `worker` IS sonnet/medium, so address it
  // by agentType and inherit its maxTurns, tool surface and operating rules for free.
  // (An earlier version of this sketch passed {model:'sonnet', effort:'medium'} here and
  // called it tuning — it is worker's frontmatter verbatim, so it tuned nothing and only
  // dropped the tier's guarantees. Reach for bare opts when you need a value a definition
  // does not offer, such as effort: 'max'.)
  (file) => agent(`Review ${file} for correctness bugs. Return each finding.`,
    {phase: 'Find', schema: FINDINGS, agentType: 'intelligent-delegate:worker'}),

  // Classification: short, independent input, no file read. Addressed by agentType, so
  // it gets omitClaudeMd and the 6-tool surface too — `{model: 'haiku'}` alone would buy
  // the price and keep the all-tools prefix.
  (found, file) => found
    ? agent(`Assign each finding a severity of high, medium or low. Findings: ${JSON.stringify(found.findings)}`,
        {phase: 'Triage', label: `triage ${file}`, schema: TRIAGED,
         agentType: 'intelligent-delegate:mechanical'})
    : null,

  // Verification: a different job from generation. Same model, higher effort — which is
  // exactly what `inspector` is (sonnet/high, read-only). An earlier version of this
  // sketch sent these refuters to `reviewer`; that is `model: inherit`, so in an Opus
  // session every per-finding refuter was an Opus agent. Refuting one named claim is a
  // narrow, bounded read: it is `inspector` work. Escalate the tie-break, not the panel.
  async (tri, file) => {
    if (!tri) return null
    const votes = await parallel(tri.triaged.map((f, i) => () =>
      agent(`Try to refute this claim about ${file}: ${f.claim}. Default refuted=true if uncertain.`,
        {phase: 'Verify', label: `refute ${i}`, schema: VERDICT,
         agentType: 'intelligent-delegate:inspector'})))
    const live = votes.filter(Boolean).filter(v => !v.refuted)
    return {file, survived: live.length, total: tri.triaged.length}
  },
)

const clean = reviewed.filter(Boolean)
log(`${clean.length}/${targets.length} targets reviewed`)
return clean
```

`.filter(Boolean)` appears twice because `agent()` returns `null` when the user skips it
or it dies after retries, and a stage that throws drops that item to `null` for the rest
of the pipeline. Nothing in a workflow script may call `Date.now()`, `Math.random()`, or
argless `new Date()` — they throw. Vary agents by index or label, never by randomness;
sample deterministically with `slice`.

## Sketch: build → review → fix, the shape that keeps getting mis-tiered

This is the shape of all four 2026-10-08 scripts, and the shape the Workflow tool's own
canonical example shows — with the tiers it should have had. Copy this rather than the
tool's example, which omits `agentType` on its build stage.

```js
export const meta = {
  name: 'build-and-verify',
  description: 'Generate each artifact, review it against its source, fix what review found',
  phases: [
    {title: 'Build', detail: 'one artifact per item', model: 'sonnet'},     // drafter
    {title: 'Review', detail: 'check each against its source', model: 'sonnet'}, // inspector
    {title: 'Fix', detail: 'apply confirmed corrections', model: 'sonnet'},  // worker
  ],
}

const VERDICT = {type: 'object', required: ['clean'],
  properties: {clean: {type: 'boolean'}, findings: {type: 'array', items: {type: 'string'}}}}

const ITEMS = args && args.length ? args : []

const results = await pipeline(
  ITEMS,
  // GENERATE. Writes a substantial artifact from supplied source material. `drafter` is
  // sonnet at HIGH effort with Edit/Write — the rung this used to lack, which is why it
  // used to land on the session model.
  (it) => agent(`${it.brief}\n\nWrite to: ${it.path}`,
    {label: `build:${it.name}`, phase: 'Build',
     agentType: 'intelligent-delegate:drafter'}),

  // VERIFY. A different job from generation, so a different tier — and read-only, so it
  // cannot "helpfully" edit what it is reviewing. A `schema` makes the verdict machine-
  // readable, which is free validation at the seam.
  (built, it) => agent(
    `Review ${it.path} against its source. Report only defects you can demonstrate.`,
    {label: `review:${it.name}`, phase: 'Review', schema: VERDICT,
     agentType: 'intelligent-delegate:inspector'}),

  // FIX. Now fully specified — the findings say what to change — so this is the cheapest
  // tier that still writes with comprehension. Skip the stage entirely when review was
  // clean; an agent that has nothing to do still costs a cold start.
  (verdict, it) => {
    if (!verdict || verdict.clean) { log(`${it.name}: clean`); return {item: it.name, fixed: false} }
    return agent(
      `Apply these confirmed corrections to ${it.path}:\n${verdict.findings.join('\n')}`,
      {label: `fix:${it.name}`, phase: 'Fix', agentType: 'intelligent-delegate:worker'})
      .then(() => ({item: it.name, fixed: true, findings: verdict.findings}))
  },
)

// ONE cross-cutting pass earns the escalation: it is the call that gates the result, it
// must reason over every artifact at once, and a miss here is silent. Note it is one
// agent, not one per item — that is what makes the escalation affordable.
phase('Gate')
const gate = await agent(
  `Read every artifact listed and find CROSS-FILE problems only: contradictions between
   files, a claim in one that another refutes, coverage gaps across the set.`,
  {label: 'cross-cutting-gate', phase: 'Gate',
   agentType: 'intelligent-delegate:reviewer'})

return {results: results.filter(Boolean), gate}
```

**Why this costs roughly half of the all-session-model version.** Three of the four stage
kinds are pinned to Sonnet, and the one `inherit` stage runs **once** instead of once per
item. The escalation is spent where failure is silent and cross-cutting, which is the rule
in `model-selection.md` → "Escalate on blast radius, not on difficulty."

**Pipeline, not parallel.** Each item's review starts the moment its build finishes; item
two's build does not wait for item one's review. The only barrier is the gate, which
genuinely needs all of them.
