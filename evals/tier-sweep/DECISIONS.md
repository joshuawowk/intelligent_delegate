# Tier-sweep decision rules — written before the sweep ran

Committed before any sweep data existed, so that the rules could not be fitted to the
result. `git log --follow` on this file against the commit that adds `results/` is the
check.

The sweep is small — five reps per cell, four synthetic tasks, one session — so every
rule below is conservative in the same direction: **a tier's default changes only when
the cheaper or faster cell is no worse on quality, not when it is merely close.** Where
a rule is not met, the 0.3.0 default stands and the result is recorded as a candidate.

Arms: `haiku`, `sonnet` and `opus`, each at `low`, `medium`, `high` and `xhigh` — twelve
arms, four tasks, five reps, 240 runs. `max` is not run: no tier pins it.

Scores are each task's grader output in [0, 1]. "Mean" and "min" are over the reps of one
arm on one task, after voided runs are removed. Speed is mean seconds from first to last
transcript record; cost is priced from per-request usage at the rates in
`../facts-2026-10-09.md`.

## D1 — `mechanical`: which effort

The tier declares none today and so runs at the session's. Candidates: `haiku/low`,
`haiku/medium`. Task: t1.

**Rule.** Take the lowest effort whose t1 mean is ≥ 0.98 and whose min is ≥ 0.95. If
neither qualifies, take `haiku/medium` and record that t1 did not clear the bar.

`haiku/xhigh` is the before: it is what the tier did in an `xhigh` session. It is
reported, not chosen from.

## D2 — a Haiku tier for reading, or not

0.3.0 has no cheap tier for "read a lot, return a little" — the commonest delegation
shape — because Haiku 4.5 had a 200K wall and no effort. Both are gone. Whether Haiku 5.5
*does the work* is a separate question, and t2 is the test.

**Rule.** Add a read-only Haiku tier if and only if some Haiku arm on t2 has a mean
within 0.05 of the best Sonnet arm's mean **and** a min ≥ 0.80 **and** is either at least
25% faster or at least 5× cheaper than that Sonnet arm. Its effort is the lowest Haiku
effort meeting the first two conditions. Otherwise ship no such tier and say why.

## D3 — `inspector`: `high` or `medium`

Ships at `sonnet/high`. The Sonnet 5.5 migration guidance says verification holds at lower
effort. Task: t3, scored F1, where a finding is credited only if its repro passes on a
correct ledger and fails on the single-defect variant.

**Rule.** Drop to `medium` only if `sonnet/medium`'s t3 mean F1 is within 0.03 of
`sonnet/high`'s **and** it finds no fewer hard defects in total across reps **and** it is
at least 20% faster. Otherwise keep `high`.

A Haiku arm matching Sonnet on t3 is recorded as a candidate and changes nothing here:
moving a judgment tier down a model on n=3 is not a call this sweep can support.

## D4 — `worker` and `drafter`

`worker` ships at `sonnet/medium`, `drafter` at `sonnet/high`. Tasks: t1 and t4.

**Rule.** Both stand unless a lower Sonnet effort matches the shipped one on **both**
tasks — mean within 0.01, min no lower — while being at least 20% faster. `drafter` may
only move to `medium` by this rule if D3 also moved `inspector`, so that the default
generate and verify rungs stay paired at one effort.

## D5 — `reviewer` and `builder`

Ship at `inherit/high`. The four `opus` arms are run on all four tasks as the
session-model reference.

**Rule.** No change, whatever the result. These tiers are reached only through an
escalation predicate — a blast radius, an absence proof, a verdict that will not be
re-checked — and none of the four tasks has that shape. The data is reported so that the
price and latency of escalating are known, not so that the escalation tiers can be tuned
on work they are not meant for.

## D6 — `judge`

Not measured. Stays `opus/xhigh`.

## D7 — the effort grid, reported and not decided from

0.3.0 argued from an effort-cost index that `sonnet/xhigh` and `opus/high` cost about the
same. That index described Sonnet 5 and Opus 5 and is retired. The twelve arms replace
the arithmetic with a measurement: seconds, dollars and score for every cell. It is
published as measured. No tier default is derived from a cell that D1-D5 do not name.

## Saturation — noted from the smoke test, before the sweep

A three-run smoke test of t3 (one run each of `haiku/low`, `sonnet/medium`,
`opus/medium`), made to check that the repro mechanics worked, scored the Sonnet and Opus
runs at 1.0. If the sweep shows the same for two arms a rule compares, the task is
**saturated** for that pair. It then shows that the cheaper cell is sufficient for work of
this difficulty, and it shows nothing about harder work.

A rule met on a saturated task may still move a default. t3 is deliberately the shape of
`inspector`'s own mandate — a bounded check of an artifact against its source — and review
that is harder than that is `reviewer`'s job, which D5 leaves alone. But the result is
then reported as saturated, in that word, everywhere it is cited, and the tier's
escalation predicates are not loosened on the strength of it.

The fixture was not made harder in response. It was hardened once already, before any
rule was written; doing it again after seeing three scores would be choosing the result.

## What would void a result

- An arm with fewer than 3 surviving reps on a task is reported as incomplete and decides
  nothing.
- If more than 10% of runs are void, the voids are investigated before any rule is
  applied.
- **t3 audit.** `analyze.py` lists every finding that earned no credit, with the reason.
  Each is read. If one is a real defect of the fixture — the reference ledger itself
  contradicts `SPEC.md` — the spec or the reference is corrected and t3 is re-run in full;
  nothing is re-graded by hand.
- A finding is never credited by reading it. There is no keyword list and no judge: the
  repro passes on the reference and fails on a variant, or it does not.
