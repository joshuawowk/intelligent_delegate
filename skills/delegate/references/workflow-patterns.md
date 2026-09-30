# Workflow patterns: shape, then tier

Routing already concluded "this needs a Workflow." Two decisions remain: which
**shape**, and what **tier** each stage runs at. The second one is where the money is.

Tier shorthand used throughout — these are just `agent()` opts:

- **mechanical** — `{model: 'haiku', effort: 'low'}`
- **worker** — `{model: 'sonnet', effort: 'medium'}`
- **builder** — `{effort: 'high'}` plus write tools; omitting `model` inherits the session model
- **reviewer** — `{effort: 'high'}`; omitting `model` inherits the session model
- **judge** — `{model: 'opus', effort: 'xhigh'}`

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
    {title: 'Triage', detail: 'cheap severity classification', model: 'haiku'},
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
  // Generation: reads the whole file, open-ended. Worker tier — same model as the
  // verify stage below, so the model-scoped cache survives across the pipeline.
  (file) => agent(`Review ${file} for correctness bugs. Return each finding.`,
    {phase: 'Find', schema: FINDINGS, model: 'sonnet', effort: 'medium'}),

  // Classification: short, independent input, no file read. Mechanical tier.
  (found, file) => found
    ? agent(`Assign each finding a severity of high, medium or low. Findings: ${JSON.stringify(found.findings)}`,
        {phase: 'Triage', label: `triage ${file}`, schema: TRIAGED, model: 'haiku', effort: 'low'})
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
