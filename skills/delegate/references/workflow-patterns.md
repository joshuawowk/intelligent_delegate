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

| You want | Write | Bare-opts form, and what it silently loses |
|---|---|---|
| mechanical | `{agentType: 'intelligent-delegate:mechanical'}` | `{model: 'haiku'}` buys Haiku pricing but **not** `omitClaudeMd`, the 6-tool allowlist or `maxTurns: 12` — and tool surface is the lever that measured **4.4× the input for an identical answer** (`model-selection.md`, "The tool surface is the biggest lever"). No `effort` either way; Haiku accepts none. |
| worker | `{agentType: 'intelligent-delegate:worker'}` | `{model: 'sonnet', effort: 'medium'}` — loses `maxTurns: 25` and the operating rules |
| reviewer | `{agentType: 'intelligent-delegate:reviewer'}` | `{effort: 'high'}` **does not give you `reviewer`.** No `maxTurns`, no read-only tool surface, no return-value contract — and it inherits the session model, so it is not a downgrade at all |
| builder | `{agentType: 'intelligent-delegate:builder'}` | none worth using: the point of this tier is its Edit/Write surface, and `tools` is not settable through opts |
| judge | `{agentType: 'intelligent-delegate:judge'}` | `{model: 'opus', effort: 'xhigh'}` — reach for opts here only when you need `effort: 'max'`, which frontmatter cannot express |

Pass bare `{model, effort}` deliberately — for `max` effort, when no shipped definition
fits, **or when the stage needs more turns than the tier budgets** — never as shorthand for
a tier.

### The turn cap is the constraint that decides this

`agentType` brings `maxTurns` with it, and that cap is enforced mid-task: the harness ends
the turn, so an agent cannot "just wrap up" — including by emitting its `schema` call. A
capped stage returns nothing and everything downstream of it silently gets no work.

**Measured, 2026-09-30 — this is what killed a 19-agent run.** Every agent used
`agentType: 'intelligent-delegate:reviewer'` (cap 20) or `:judge` (cap 25). Distinct API
calls per agent:

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

For comparison, untiered agents doing the same review shape in the follow-up run used
15, 18, 18, 20, 22, 29, 34, 35, 36 and 45 calls. Four of ten exceeded 20. Under the
shipped `reviewer` cap, those four would have been guillotined.

So before routing a stage to a tier, ask what it costs in **turns**, not just tokens:

- Repo-scale review, broad-surface audits, "survey then analyse" — budget well over 20
  turns. As shipped, `reviewer` cannot fund that. Either pass bare opts deliberately and
  accept losing the tier's other guarantees, or raise `maxTurns` in the definition.
- `maxTurns` is frontmatter-only; no `agent()` opt raises it for one stage.
- Whatever cap applies, **leave a turn for the return**. A schema stage that spends its
  last turn reading one more file fails the stage outright.

**Measured, 2026-09-30.** A 73-agent audit fan-out passed only `{label, phase, schema,
effort}` at all four call sites. Every agent logged `agentType: "workflow-subagent"` and
ran `claude-opus-5`: the tiers were never engaged, including a 9-agent stage whose prompt
was pure schema transcription. A 19-agent run in the same session passed
`agentType: 'intelligent-delegate:reviewer'` on every call — correct usage — and *also*
ran all-Opus, because `reviewer` inherits. Both paths cost Opus rates: roughly **$100–130** for 92
agents at standard cache rates, against ~$45–50 for the same tokens on Sonnet.

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
Smell test: `const a = await parallel(...); const b = transform(a); await parallel(b.map(...))`
— if `transform` has no cross-item dependency, that barrier is unearned.
## The named shapes

- **Adversarial verify** — N independent skeptics per finding, each prompted to *refute*,
  defaulting to refuted when uncertain. Kill on majority refutation. For: plausible-but-wrong
  findings that survive a single confirm-shaped check.
- **Perspective-diverse verify** — same fan-out, but each verifier gets a distinct lens
  (correctness / security / perf / does-it-reproduce). For: findings that can fail in more
  than one way, where redundancy would miss the mode nobody looked for.
- **Judge panel** — generate N attempts from different angles (MVP-first, risk-first,
  user-first), score with parallel judges, synthesize from the winner while grafting the
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

| Shape | Drop to mechanical | Mid tier (`worker` pins sonnet; `reviewer` inherits) | Earns judge |
|---|---|---|---|
| Adversarial verify | — | refuters at `effort: 'high'` | tie-break when the vote splits |
| Perspective-diverse verify | — | each lens at `effort: 'high'` | the lens that gates a release |
| Judge panel | — | the N generators | the final synthesis |
| Loop-until-dry | per-round severity/triage classification | the finders | final confirm pass only |
| Multi-modal sweep | — | each arm (`agentType: 'Explore'`), then the merge | rarely |
| Completeness critic | — | — | the critic itself, `effort: 'xhigh'` |

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

**Observed near-miss, 2026-09-30.** In the 73-agent run above, the reviewer covering
secrets and credential exposure emitted "The report is durable at 2716 words. Let me have
the advisor review before finalizing." — 86 characters, under a 200-character guard. Its
nine sibling reviewers returned 21k–38k characters each. Had its turn ended on that line,
the only security review in the fan-out would have been dropped on a length check, with no
log line and no retry. The guard is the single-point-of-failure, not the agent.

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
    {title: 'Find', detail: 'one finder per target file', model: 'sonnet'},
    {title: 'Triage', detail: 'cheap severity classification', model: 'haiku'},  // tier pins haiku
    {title: 'Verify', detail: 'adversarial refutation', model: 'sonnet'},
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
  // Generation: reads the whole file, open-ended. Bare opts on purpose — this stage
  // pins the same model as the verify stage below so the model-scoped cache survives
  // across the pipeline, which `agentType: '...:worker'` (medium, fixed) would not let
  // us tune. Deliberate bare opts, not shorthand for a tier.
  (file) => agent(`Review ${file} for correctness bugs. Return each finding.`,
    {phase: 'Find', schema: FINDINGS, model: 'sonnet', effort: 'medium'}),

  // Classification: short, independent input, no file read. Addressed by agentType, so
  // it gets omitClaudeMd and the 6-tool surface too — `{model: 'haiku'}` alone would buy
  // the price and keep the all-tools prefix.
  (found, file) => found
    ? agent(`Assign each finding a severity of high, medium or low. Findings: ${JSON.stringify(found.findings)}`,
        {phase: 'Triage', label: `triage ${file}`, schema: TRIAGED,
         agentType: 'intelligent-delegate:mechanical'})
    : null,

  // Verification: a different job from generation. Same model, higher effort.
  async (tri, file) => {
    if (!tri) return null
    const votes = await parallel(tri.triaged.map((f, i) => () =>
      agent(`Try to refute this claim about ${file}: ${f.claim}. Default refuted=true if uncertain.`,
        {phase: 'Verify', label: `refute ${i}`, schema: VERDICT, model: 'sonnet', effort: 'high'})))
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
