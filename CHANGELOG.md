# Changelog

What changed in each release and why. `skills/delegate/SKILL.md` is loaded into context
every time the skill fires, so the history that used to be narrated there lives here.

## 0.4.0 — 2026-10-09

The aliases moved to the 5.5 generation, and most of what 0.3.0 reasoned from stopped
being true. This release re-verifies the facts, measures what it used to compute, and
re-sets the tiers from the measurement. Purpose is restated: **speed, result quality and
cost together** — 0.3.0 argued almost entirely from price.

**Verified** (`evals/facts-2026-10-09.md`), against the Claude Code 2.1.295 catalog and by
ten runtime probes:

- `sonnet`, `haiku` and `opus` now resolve to the 5.5 models. No pin needed changing.
- Haiku 5.5 has a 1M window and takes an effort setting. "Haiku takes no effort" and "the
  Haiku 200K context trap" described Haiku 4.5.
- Haiku 5.5 is a twentieth of Sonnet's price, not half. Above 100K prompt tokens it bills
  five times its base rate.
- Frontmatter `effort:` is honoured at runtime — a caveat this repo had carried since 0.2
  — and **an omitted one inherits the session's**, not a default.
- The `Agent` tool takes `effort`, and it overrides the definition's.
- Cache-read rates for Opus 5.5 and Fable 5.1 had been read as multipliers when they are
  dollar rates; both are cheaper than the standard fraction, not dearer.

**Measured** (`evals/tier-sweep/`): 240 graded runs, twelve model x effort arms on four
task shapes, none void, with decision rules committed before the data.

- Quality was at or near the ceiling in every cell, so the sweep ranks cells by time and
  money, where they differ by multiples.
- Effort is the largest speed lever: `xhigh` took 2.9-3.9x as long as `medium` on the
  same model. `low` saved 8-17% and is where every Sonnet and Opus miss happened.
- Sonnet is the fast model and Haiku the cheap one. Haiku writes about three times the
  output tokens, so at `medium` it took 1.6x as long and it is about 10x cheaper measured,
  against 20x on price.
- A subagent that names no tier inherits the session — here `opus/xhigh`: 6.2x the time
  and 6.6x the cost of `sonnet/medium` for the same score.

**Changed**:

- `mechanical` pins `effort: low`. It declared none and had been running at the session's
  — Haiku at `xhigh`, 2.5x slower for the same result.
- `inspector` moves from `high` to `medium`: 39% faster on a seeded-defect review with
  every defect still found. That task was saturated, and the docs say so. The step above
  it is now `effort: 'high'` on the call, not another tier.
- New tier `scout` — Haiku at `low`, read-only, for pulling known facts out of a large
  input that the caller can check. It qualified on cost, not speed, and measured slightly
  less exact, so it is not a stage default. Eight tiers.
- `worker`, `drafter`, `reviewer`, `builder` and `judge` keep their model and effort.
  `drafter` at `medium` is a recorded candidate.
- The cost ladder is re-based on Haiku 5.5; the effort x model arithmetic, which priced
  Sonnet 5 and Opus 5, is retired in favour of the measured grid.
- The gate on a Haiku tier is no longer a price break-even — a failed Haiku attempt is
  nearly free — but whether you can tell quickly that the result is wrong.
- The hook warns when a waived `agent()` call names no effort, and its stage table and
  deny text are corrected.
- Agent descriptions are written as quoted YAML; several contained a colon-space that a
  strict parser rejects.
- `evals/measure_triggers.py` loads the working tree explicitly and proves it from the
  session's own init event. It had printed "measuring the working tree" unconditionally,
  which is false for a synced install.
- Behavioural eval cases 2, 4 and 8 rested on reversed facts and are rewritten; cases are
  added for effort inheritance and speed.

**Verified**, each against this checkout in fresh sessions that prove which copy they
loaded:

- `evals/probe_tiers.py` — 8 of 8 tiers ran the model and effort they declare, each under
  a parent at `max` and on a model that tier does not pin, so a lost pin could not pass by
  inheriting.
- `evals/probe_hook.py` — 4 of 4 paths: the hook returned deny for an untiered workflow
  and no agent ran; it returned nothing for a tiered one, and both notes where due.
- `evals/measure_triggers.py` — the rewritten description fired on 16 of 16 positives and
  0 of 8 negatives at n=3, with all 72 calls confirmed.
- `evals/behavioural.workflow.js` — 15 routing cases, three runs each, answered from
  `SKILL.md` alone, on the text as shipped: 185 of 192 expectation checks passed and 39 of
  45 runs passed every one. No failure was a wrong route, and the run before it had the
  same totals with different cases missing — which is what noise looks like. The first run found one real tension in the skill
  (case 5), fixed, and six over-specified rubric lines in four cases, rewritten — three of
  which had failed in only two runs of three. `evals/README.md` lists every line changed.

**Not verified, and said so where it matters**: anything about quality on work with a
blast radius, an unstated invariant or an absence to prove; `max` effort's cost; fast
mode; what an advisor consult costs; `judge` on adjudication.

**Method worth keeping**: two adversarial reviews of the sweep's graders ran before the
sweep did, and both found them broken — the second in both directions at once. Review
findings are now graded by running a repro against a correct ledger and a single-defect
variant, not by reading prose. `evals/tier-sweep/test_graders.py` keeps every exploit.

## 0.3.0 — 2026-10-08

- Added `drafter` and `inspector`, both Sonnet at `high`. The ladder had gone from
  `worker` (sonnet/medium) straight to the `inherit` tiers, so "more than `worker`
  deserves" had one destination: the session model. Three measured fan-outs ran entirely
  on Opus partly for that reason.
- Added a `PreToolUse` hook that denies a `Workflow` whose `agent()` calls carry no
  `agentType`. The guidance against that had been correct and ignored three times.
- Split the tier decision into two gates — escalation (pinned Sonnet to the session
  model) and the Haiku gate — after the single gate was found to route every review stage
  to `reviewer`.
- Rewrote the hook around one scanner after a review demonstrated four false denies, and
  made it allow whatever it cannot read.
- Added behavioural evals for the tiering failure, and recorded end-to-end hook probes.

## 0.2.0 — 2026-10-01

- Fixed the guidance that produced a 92-agent all-Opus fan-out: an `agent()` call with no
  `agentType` is not a cheap tier, it is no tier.
- Raised `reviewer` `maxTurns` 20 -> 50 and `judge` 25 -> 50 on measured turn demand: 11
  of 19 agents in one run had landed exactly on their cap and returned nothing.
- Gave four tiers `ToolSearch` so MCP work is routable, and documented what blocks it
  when a session disables the tool.
- Made the trigger harness compare content rather than a recorded SHA, stop counting
  timeouts as misses, and report from one real n=3 run.
- Applied a five-dimension adversarial audit (33 fixes) and de-duplicated `SKILL.md`.

## 0.1.0 — 2026-09-30

- First release: the `delegate` skill, three reference files, and tiered agent
  definitions (`mechanical`, `worker`, `reviewer`, `judge`, then `builder`), built on the
  observation that the `Agent` tool took a model but no effort, so an effort choice was
  reachable only through a definition that pinned it.
- Measured that tool surface, not model tier, is the largest input lever: a six-tool
  definition used a quarter of the input of an all-tools agent on an identical task.
- Found that a session's advisor is attached to every subagent and cannot be suppressed
  per agent.
- Renamed the plugin id to kebab-case `intelligent-delegate`; the repo keeps its underscore.
