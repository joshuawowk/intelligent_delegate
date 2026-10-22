# Changelog

What changed in each release and why. `skills/delegate/SKILL.md` is loaded into context
every time the skill fires, so the history that used to be narrated there lives here.

## Releases track `main` — 2026-10-22

The manifests no longer carry a `version`. Claude Code and claude.ai detect updates by
comparing the computed version, `plugin.json` first; with a pinned `0.4.0` the account's
synced copy stayed at its 2026-10-09 state through every later merge. With no `version`
the commit SHA is the version, so each merge to `main` ships. Headings here name releases;
`claude plugin validate --strict` now warns on the missing field by design.

## 0.5.0 — 2026-10-22

0.4.0 tiered subagents correctly in the first real sessions audited after it shipped, and
the bill was still dominated by the one agent the skill never priced: the orchestrator.
This release measures that, re-checks every fact against the 2026-10-22 Anthropic docs, and
fixes what the docs contradicted. Evidence: `evals/facts-2026-10-22.md`.

**Measured**:

- A 50-minute Opus 5.5 / `xhigh` cloud session that tiered every agent on `drafter`:
  orchestrator $16.47 of $21.77 (76%), 44.6M cache-read tokens over a ~395K context; the
  Sonnet agents that did the building, $5.29 (Claude Code's own `modelUsage.costUSD`).
- This release's own build session, 16 Sonnet subagents: orchestrator 74% ($16.57 of
  $22.51 at list prices, 22 background wake-ups, mean context 341K) —
  `evals/session-audit-2026-10-22.json`. The pattern reproduced while documenting it.
- Routing regression on the rewritten skill: 19 cases (15 existing, 4 new), one Opus
  answerer and a Sonnet grader, single run — 75 of 80 expectation checks, 16 of 19 cases
  clean, every new case clean. The misses traced to three cues condensed out of the skill;
  they were restored and the three cases re-run: case 5 clean, cases 4 and 13 each missing
  only "call-site effort overrides the definition's", which the skill states twice.
  A single run, not the 0.4.0 three-run protocol.

**Added**:

- `SKILL.md` → "The orchestrator is a cost centre", in the first 5K tokens (the part of
  an invoked skill that survives compaction): why every request and every background
  completion re-reads the context, and six levers in the order they pay — Workflow over N
  background `Agent` calls, bytes out of the main context, compaction at phase boundaries,
  orchestrator effort, cache lifetime, and measurement.
- `scripts/delegation_audit.py` and the user-invoked `/intelligent-delegate:audit`: split
  a session's spend into orchestrator and each subagent, and flag eight patterns. Prices
  from the 2026-10-22 pricing table; fast mode and Haiku's 100K multiplier applied.
  24 tests in `scripts/test_delegation_audit.py`.
- `references/orchestrator-cost.md`: the measurement, wake-up and rebuild arithmetic per
  model and context size, what starts an orchestrator request, the levers with sources.
- `SKILL.md` → "Settings that silently override the tiers": `CLAUDE_CODE_EFFORT_LEVEL`,
  `CLAUDE_CODE_SUBAGENT_MODEL_FORCE`, `/model` moving the inherit tiers, inherited thinking,
  fallback chains, and the advisor.
- Hook: notes an `Agent` call with no tier and no model; warns once per session when either
  override variable is set. 64 tests (was 53).
- `references/model-selection.md` → "Platform features checked 2026-10-22": fast mode, task
  budgets (not supported in Claude Code), batch (API only), per-message effort, compaction,
  thinking, `max` effort, tool search — and whether each reaches Claude Code.
- Anti-patterns 18-20: an orchestrator that reads everything; N background `Agent` calls
  for one fan-out; a mid-orchestration `/model` switch. Behavioural cases 16-19.

**Fixed — the docs contradicted 0.4.0**:

- Sonnet 5.5 cache reads are $0.10/MTok (0.05x), not $0.20. Confirmed against Claude
  Code's own cost for a real session to the cent.
- "Dropping a tier forfeits cache reuse, because caches are model-scoped" — wrong for
  subagents, which never read the orchestrator's cache. It holds for a main-loop `/model`
  switch. Workflow siblings share a prefix only with identical model, effort, agent type,
  tools, schema and cwd.
- "A returned Agent call is not live: re-brief a fresh one" — `SendMessage` resumes a
  finished subagent with its history (not Explore or Plan).
- `Explore` runs on the session's model; "cheapest cold start" was true of its prefix only.
- `disallowedTools` is applied alongside `tools:` per the current docs; the earlier claim
  that it is ignored came from a 2.1.29x schema string.
- Workflow concurrency is "up to 16, fewer with fewer CPUs", tunable; `min(16, CPUs − 2)`
  is not documented.
- A worktree branches from the default branch, not your HEAD.
- The hook's notes went to `systemMessage`, which only the user sees; they now also go to
  `additionalContext`, which reaches the model.
- "'Think hard' sets nothing" sharpened: prompt text does not set effort but can nudge
  thinking, and `ultrathink` is a recognised per-turn keyword.
- Advisor: priced per consult at the advisor's rates, not across the whole fan-out;
  observed as Opus 5.5 in the 2026-10-22 sessions; `advisorModel` is also a setting.

**Changed**:

- `SKILL.md`: 541 → 465 lines, description 1,214 → 915 characters parsed (the limit is 1,024),
  third person; the retry table moved to `model-selection.md`, the per-tier prose to the
  catalog.
- Agent bodies — each one's system prompt — cut to identity, wrong-tier list, rules and
  return contract; rationale and measurements live in the catalog. The writing tiers got
  the Sonnet/Haiku 5.5 guides' scope paragraph ("stop and report; don't add what wasn't
  asked") and real-check paragraph; the two Haiku tiers the keep-working sentence.
  Frontmatter is byte-identical, so the 0.4.0 tier probes still describe these tiers.

**Not verified, and said so where it matters**: the orchestrator levers' effect on a
measured session (only the problem is measured, not each fix); fast mode; `max` effort;
an advisor consult's cost; nested coordinators.

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
