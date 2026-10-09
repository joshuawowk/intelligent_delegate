# intelligent-delegate 0.4.0 — design spec

This is the authoritative brief for rewriting the plugin. Where an existing file
disagrees with it, this wins. Where this disagrees with a source below, the source wins
and you should say so in your return value.

## 0. Sources, in order of authority

1. `evals/facts-2026-10-09.md` — model catalog facts and nine runtime probes. Verified.
2. `evals/tier-sweep/RESULTS.md` — measured speed, quality and cost per model x effort.
3. This spec — decisions, canonical wording, and the only derived numbers permitted
   (section 5 from prices, section 6 from the sweep).
4. `evals/audit-0.4.0/<group>.json` — per-file inventory of what is stale and what must
   survive, from an 18-agent audit of the 0.3.0 tree at `42ac24d`.

### The numbers rule — the one most likely to be broken

**No number may appear in anything you write unless it is in source 1, source 2, or
section 5 or 6 of this spec.** Not a ratio, not a percentage, not a multiplier, not a
break-even. If a sentence needs a number that no source gives, the sentence is wrong for
this release: rewrite it qualitatively or cut it. In particular **do not compute an
effort multiplier for Sonnet 5.5, Opus 5.5 or Haiku 5.5** — none publishes an
`effort_cost_index`, and the Sonnet 5 / Opus 5 indices do not describe them. Dated
historical measurements already in a file ("2026-09-30: 19/19 on claude-opus-5") are
history: keep them exactly, as history.

**Say which 20x.** Haiku 5.5 is 20x cheaper than Sonnet 5.5 on *price*. Per *task* it
measured about 10x cheaper, because it writes about three times the output tokens. Both
are true and both are citable; a Haiku/Sonnet cost ratio that does not say which it is, is
wrong. Write "20x on price, about 10x measured", or one of the two with its label.

### The other standing rules

- **Purpose.** This plugin optimizes **speed, result quality and cost together.** 0.3.0
  framed nearly everything as thrift. Wherever a passage justifies a choice by price
  alone, give the speed and quality side too — but do not pad: one clause, not a paragraph.
- **Voice.** Match the file you are editing: direct, evidence-first, dated provenance,
  no marketing. Say what was measured and what was merely judged, in those words.
- **Do not narrate version history in `SKILL.md`.** It is loaded into context every time
  the skill fires. "0.3.0 exists to fix…", "this file previously got wrong…" belongs in
  `CHANGELOG.md`. State the current rule and its reason.
- **Keep what is true.** Every `still-true-keep` item in your audit file must survive.
  Over-correction is a defect of the same size as a stale claim.
- **Do not grow files.** Replace, do not append. A rewritten file should be no longer than
  the one it replaces unless this spec adds a section to it.

## 1. What changed in the world

Read the facts file for the evidence; these are the five that drive every edit.

1. **The aliases moved.** `sonnet` -> `claude-sonnet-5-5`, `haiku` -> `claude-haiku-5-5`,
   `opus` -> `claude-opus-5-5`, `fable` -> `claude-fable-5-1`. No pin in this repo needed
   changing to reach them; the reasoning written around the pins did.
2. **Haiku 5.5 is a different kind of tier.** 1M context (was 200K). Accepts effort
   `low`..`max` (Haiku 4.5 accepted none). $0.10 in / $0.50 out — a twentieth of Sonnet,
   where Haiku 4.5 was half. One real constraint replaces the old wall: above 100K prompt
   tokens it bills 5x its base rate, which is still a quarter of Sonnet.
3. **Frontmatter `effort:` is honoured at runtime, and an omitted one inherits the
   session.** Both probed. Precedence: call-site > definition > session. Nothing falls
   back to the catalog's `default_effort`.
4. **The `Agent` tool takes `effort`**, and it overrides the definition's.
5. **No 5.5 model publishes an effort-cost index** — not Sonnet 5.5, Opus 5.5 or Haiku
   5.5. (Fable 5.1 does; it is not a tier.) The effort x model arithmetic in 0.3.0 priced
   Sonnet 5 and Opus 5. It is retired, and replaced by measurement (source 2), not by new
   arithmetic.

## 2. What changes in the plugin

Each follows from section 1 or from the sweep. `evals/tier-sweep/DECISIONS.md` holds the
rules D1-D6 as committed before the sweep ran; `RESULTS.md` shows each one applied.

1. **Every tier pins an effort.** `mechanical` declared none and so ran at the session's:
   Haiku at `xhigh`, 2.5x slower than at `low` for the same score. It now says
   `effort: low` (D1).
2. **`inspector` moves from `high` to `medium`** (D3) — 39% faster on a seeded-defect
   review with every defect still found in every run. That task was **saturated**; say so
   wherever the number is used. The rung above it is no longer another tier: it is
   `effort: 'high'` passed on the call, which overrides the definition (probe row 6).
   `reviewer` is reached only through an escalation predicate, as before.
3. **A new tier, `scout`** (D2) — Haiku at `low`, read-only, for pulling named facts out
   of a large input. It qualified on cost and not on speed, and it is the one cell that
   was measurably less exact. It is **not a stage default.** It has one shape: extract
   known facts from a large input, where the caller can check the answer.
4. **`worker`, `drafter`, `reviewer`, `builder`, `judge` keep their model and effort**
   (D4, D5, D6). `drafter` at `medium` is a recorded candidate, not a change.
5. **Eight tiers, not seven.** Every count in the repo moves.
6. **The `Agent` tool's `effort` is used.** `SKILL.md` instructs the caller to pass it on
   any call that does not go through a pinned tier, and to raise or lower a tier's effort
   at the call site instead of changing tier. The tool's own rule is that effort is set
   only when a user or a skill asks; this skill asks.
7. **Speed is a first-class axis.** A short measured section in `SKILL.md`, and the tier
   tables carry seconds as well as cost.
8. **The cost ladder is re-based** on Haiku 5.5 = 1x (section 5), and the Haiku gate
   changes from a price break-even to *can you tell quickly that the result is wrong*.
9. **The effort x model arithmetic is retired** and replaced by the measured grid.
10. **`SKILL.md` stops narrating its own history.** That moves to a new `CHANGELOG.md`.
11. **The hook** warns when a waived call names no effort (already committed, `c78afc0`),
    and its stage table is corrected.
12. **Evals**: behavioural cases 2, 4 and 8 rested on reversed facts and are rewritten;
    cases are added for effort inheritance and for speed; the trigger set gains
    speed-framed queries.
13. **Version 0.4.0**, in both manifests.

## 3. The eight tiers — frontmatter, verbatim

Use these exactly. The `description` is what a model reads to route work, so every figure
in one is from section 6 and has been checked against it.

| tier | model | effort | maxTurns | tools | writes | omitClaudeMd |
|---|---|---|--:|---|:--:|:--:|
| `mechanical` | haiku | **low** (was unset) | 12 | Read, Grep, Glob, Edit, Write, Bash | yes | yes |
| `scout` **(new)** | haiku | low | 25 | Read, Grep, Glob, Bash | no | yes |
| `worker` | sonnet | medium | 25 | Read, Grep, Glob, Edit, Write, Bash, WebFetch, WebSearch, ToolSearch | yes | no |
| `drafter` | sonnet | high | 50 | Read, Grep, Glob, Edit, Write, Bash, ToolSearch | yes | no |
| `inspector` | sonnet | **medium** (was high) | 50 | Read, Grep, Glob, Bash, ToolSearch | no | no |
| `reviewer` | inherit | high | 50 | Read, Grep, Glob, Bash, ToolSearch | no | no |
| `builder` | inherit | high | 50 | Read, Grep, Glob, Edit, Write, Bash, ToolSearch | yes | no |
| `judge` | opus | xhigh | 50 | Read, Grep, Glob, Bash, ToolSearch | no | no |

`scout`'s `maxTurns` is 25, not `mechanical`'s 12: Haiku made up to 12 requests on the
extraction task at `high`. Neither Haiku tier lists `ToolSearch`. The 0.3.0 reason — an MCP
payload could overflow a 200K window — is gone with the window. The reason that remains is
mandate: an MCP response is unbounded and shaped by a third party, and neither "convert
this by rule" nor "pull these named facts from this file" describes work against one.

One caveat on `scout`'s numbers, to be stated where they are used at length: the
extraction task ran on `inspector`'s definition — five tools including `ToolSearch`, a
50-turn cap, `CLAUDE.md` injected — with only model and effort overridden. `scout`'s own
surface is narrower, so its cold start should be no larger than what was measured. The
figures describe Haiku at `low` doing this work, not this exact definition.

### Descriptions

**`mechanical`**

> Cheapest writing tier (Haiku, low effort). Use for deterministic, fully specified work whose result is verifiable without judgment — mechanical refactors, renames applied across known files, format/lint fixes, boilerplate generation, converting records by rule and example. Cheap, not fast: on a 40-record transform it measured a tenth of `worker`'s cost and 1.4x its time, with every record right. Reach for it in a fan-out, where parallelism hides the latency; for one latency-sensitive call use `worker`. Do NOT use when the task needs design judgment, when the correct answer is not knowable from the prompt alone, or when you could not tell quickly and cheaply that the result is wrong.

**`scout`**

> Cheapest reading tier (Haiku, low effort, read-only). Use to pull named facts out of a large input — counting or locating entries in a long log, extracting fields from a changelog, finding which of many files mention something — when the answer is one you can check, or a wrong one is cheap. Cheap, not fast, and not exact: on a ten-question log extraction it measured a thirteenth of `inspector`'s cost at about the same speed, and got 48 of 50 answers right where every Sonnet and Opus run got them all. Both misses were one shape — reading the line next to a match. Reach for it in a fan-out or over a very large corpus. For one read you will act on unchecked, use `inspector`. Do NOT use for review, audit, an absence proof or any verdict, and not for work that edits files.

**`worker`**

> Default workhorse tier (Sonnet, medium effort, writes). Use for ordinary multi-step implementation and research that needs real reading comprehension but has a knowable right answer — implementing a well-scoped feature, tracing how a subsystem works, writing tests against a clear spec, migrating a known pattern across files, applying a fix a review has already specified. Sonnet at medium was the fastest cell measured with no misses: against an untiered subagent in an Opus session at xhigh it took about a sixth of the time and cost for the same score. Do NOT use for adjudicating a contested judgment call, for adversarial verification, or for work where being confidently wrong is expensive.

**`drafter`**

> Default generation tier (Sonnet, high effort, writes). Use for producing a substantial artifact from source material you supply — writing documentation from a verified evidence file, drafting a skill or runbook, implementing a well-scoped feature whose shape the brief settles, applying a pattern across targets where the brief says how each differs. This is the tier to reach for FIRST when a stage generates something. It pins Sonnet instead of inheriting the session model: in an Opus session it measured about a third of `builder`'s cost and half its time on the same work. Escalate to `builder` only when an escalation predicate fires: two readings of the brief genuinely survive, correctness rests on an invariant the brief does not state, the blast radius is security/auth/money/deletion/migrations/concurrency, or a failure would be silent to the caller. Prefer `worker` (sonnet/medium) when the brief fully specifies the output — it measured 41% faster on a spec-driven implementation at the same score — and `mechanical` when it is specified by example.

**`inspector`**

> Default inspection tier (Sonnet, medium effort, read-only). Use for ordinary review, verification and audit work — checking a generated artifact against its source, verifying a finding, per-item correctness passes in a fan-out, hunting edge cases in a bounded diff — and for a read whose answer you will act on. This is the tier to reach for FIRST when the verb is review/verify/audit. On a seeded-defect review it found every defect in every run at medium, 39% faster than at high; that task was saturated, so it shows medium is enough for a bounded check and nothing about harder review. When a bounded review needs more thoroughness, pass `effort: 'high'` on the call before reaching for another tier. It pins Sonnet instead of inheriting the session model: in an Opus session it measured a third of `reviewer`'s time and a quarter of its cost. Escalate to `reviewer` only when an escalation predicate fires — a security/auth/money/migration/concurrency blast radius, a negative or universal claim to prove, an invariant not stated in the brief, two surviving readings, or a verdict you will build many turns on without re-checking. The review/audit VERB alone is not a reason to escalate. Has no Edit or Write tools.

**`reviewer`**

> ESCALATION inspection tier — inherits the session model at high effort, so in an Opus session this IS an Opus agent: measured at 3x the time and 4x the cost of `inspector` on a bounded review, for the same result. Reach for `inspector` (sonnet/medium, read-only) FIRST for ordinary review, verification and audit work, and raise its effort before changing tier; come here only when an ESCALATION predicate fires: a security/auth/money/migration/concurrency blast radius, a negative or universal claim to prove ("nothing else writes this field"), an invariant not written in the brief, or a verdict the caller will build many turns on without re-checking. Has no Edit or Write tools. Do NOT use to write or fix code (use builder, or drafter/worker if cheaper fits), and do NOT use to pick a winner between competing options (use judge).

**`builder`**

> ESCALATION implementation tier — inherits the session model at high effort WITH Edit and Write, so in an Opus session this IS an Opus agent: measured at 2.4x the time and 3.4x the cost of `drafter` on a spec-driven implementation, for the same result. Reach for `drafter` (sonnet/high, writes) FIRST for ordinary generation and well-scoped implementation; come here only when an ESCALATION predicate fires: two readings of the brief genuinely survive, correctness rests on an invariant the brief does not state, the blast radius is security/auth/money/deletion/migrations/concurrency, or a failure would be silent to the caller. Use when an escalation predicate disqualifies drafter and worker but the job still writes code.

**`judge`**

> Adjudication tier (Opus, xhigh effort). Use only for contested calls where being wrong is expensive and cheaper tiers have already disagreed or already failed — refuting a claimed finding, choosing between competing designs, deciding whether a risky change is safe, settling a split verdict from a verifier panel. Has no Edit or Write tools. Do NOT use as a general-purpose worker: Opus at xhigh was the slowest and most expensive cell measured, about six times the time and cost of `worker` on bounded work for the same score, so routine work here is the commonest way to waste both.

## 4. Canonical wording

Reuse these sentences. Eight files saying the same thing in eight ways is how the 0.3.0
tree came to contradict itself.

- **Effort inheritance.** "A subagent that names no effort runs at the **session's**
  effort, not at a default. Every tier here pins one."
- **Precedence.** "Call-site `effort` beats the definition's, which beats the session's."
- **The price ladder.** "Haiku 1x / Sonnet 20x / Opus 40x / Fable 100x, input and output
  alike."
- **Which 20x.** "20x on price, about 10x measured — Haiku writes about three times the
  output tokens."
- **Haiku's window.** "Haiku 5.5 has a 1M window. Above 100K prompt tokens it bills 5x its
  base rate, which is still a quarter of Sonnet's."
- **Cheap, not fast.** "Haiku is the cheap model, not the fast one: at `medium` it took
  1.6x as long as Sonnet." (1.6x is the `medium` row. The gap was smaller at every other
  effort, so do not write "at the same effort".)
- **The default effort.** "`medium` is the default for bounded work on every model. `low`
  saved 8-17% and is where every Sonnet and Opus miss happened; `high` took 1.4-1.9x as
  long and `xhigh` 2.9-3.9x, and neither improved a score."
- **Raise effort before tier.** "Pass `effort: 'high'` on the call before you reach for a
  different tier. Change tier on an escalation predicate, not on a feeling."
- **The untiered cost.** "An `agent()` or `Agent` call that names no tier inherits the
  session's model **and** its effort. In an Opus session at `xhigh` that measured 6.2x the
  time and 6.6x the cost of `sonnet/medium` for the same score."
- **The detectability gate.** "A failed Haiku attempt is nearly free in dollars. What it
  costs is the wall-clock of the failed attempt and the risk nobody notices. So the gate
  on a Haiku tier is whether you can tell, quickly, that the result is wrong."
- **Saturation.** "Measured on a saturated task: it shows the cheaper cell is enough for
  work of this difficulty and nothing about harder work."
- **Purpose.** "Speed, result quality and cost, together."
## 5. Canonical derived numbers

Computed from the facts-file rates and nothing else. These, and only these, may be
quoted as derived figures.

**Price ladder, input and output alike, Haiku 5.5 = 1x:**
Haiku 5.5 **1x** / Sonnet 5.5 **20x** / Opus 5.5 **40x** / Fable 5.1 **100x**.
Equivalently Sonnet is 20x Haiku, Opus is 2x Sonnet, Fable is 2.5x Opus.
Above 100K prompt tokens Haiku 5.5 is 5x its own base, so Sonnet is then **4x** it.

**Rates, USD per million tokens:**

| Model | id | Context | In | Out | Cache read | Default effort (catalog) |
|---|---|--:|--:|--:|--:|:--:|
| Haiku 5.5 | `claude-haiku-5-5` | 1M | 0.10 | 0.50 | 0.01 | medium |
| Haiku 5.5, prompt > 100K | | | 0.50 | 2.50 | 0.05 | |
| Sonnet 5.5 | `claude-sonnet-5-5` | 1M | 2 | 10 | 0.20 | medium |
| Opus 5.5 | `claude-opus-5-5` | 1M | 4 | 20 | 0.20 | medium |
| Fable 5.1 | `claude-fable-5-1` | 1M | 10 | 50 | 0.25 | high |

Cache reads as a fraction of that model's input rate: Haiku 5.5, Sonnet 5.5 **0.10x**;
Opus 5.5 **0.05x**; Fable 5.1 **0.025x**. (0.3.0 had the last two inverted — it read the
tier name's dollar rate as a multiplier.)

**A 10-agent fan-out, each agent 40K input + 5K output (400K in, 50K out):**

| All 10 on | Input $ | Output $ | Batch $ | Per agent $ |
|---|--:|--:|--:|--:|
| Haiku 5.5 | 0.04 | 0.025 | **0.065** | 0.0065 |
| Sonnet 5.5 | 0.80 | 0.50 | **1.30** | 0.13 |
| Opus 5.5 | 1.60 | 1.00 | **2.60** | 0.26 |
| Fable 5.1 | 4.00 | 2.50 | **6.50** | 0.65 |

Input is **62%** of the bill at that 8:1 ratio.

**Break-even attempts, ignoring the cost of noticing a failure:** a Haiku run stops being
cheaper than one Sonnet run at **20** attempts and than one Opus run at **40**; a Sonnet
run stops being cheaper than one Opus run at **2**.

**Retry threshold.** Cheap-first is cheaper only while the first-pass failure rate `p`
stays under `p* = (dear - cheap) / (dear + d)`, in units of one Haiku-equivalent run
(Haiku 1, Sonnet 20, Opus 40). `d` is your own cost to notice the failure and re-brief.

| cheap -> dear | `d` = 0 | `d` = 3 | `d` = 20 |
|---|:--:|:--:|:--:|
| haiku -> sonnet | 0.95 | **0.83** | 0.47 |
| haiku -> opus | 0.97 | **0.91** | 0.65 |
| sonnet -> opus | 0.50 | **0.47** | 0.33 |

`d` = 3 is an Opus 5.5 orchestrator reading a 2K-token failed report and writing a
500-token re-brief ($0.018, against $0.0065 for the Haiku run). `d` = 20 is noticing
that costs a whole Sonnet run.

**What this table now says, and it is the opposite of 0.3.0's.** With a 2x gap, "Haiku
that fails once costs more than Sonnet that succeeds" was true. With a 20x gap it is
false on price: a failed Haiku attempt plus the Sonnet retry is 21 units against 20. A
cheap first attempt is now nearly free in dollars. What it costs is **wall-clock** — the
failed attempt's latency is paid before the retry starts — and **the risk that the
failure is not noticed at all**, where no table applies. So the gate on the Haiku tiers
is no longer a price break-even. It is: *can I tell, quickly and cheaply, that the result
is wrong?*

## 6. Canonical measured numbers

From `evals/tier-sweep/RESULTS.md` — 240 runs, 2026-10-09, Claude Code 2.1.295, an
`opus/xhigh` session, none void. Quote the grid and the per-task tables in that file
directly. The ratios below are the only *derived* measured figures permitted; each row is
computed from that file.

"all" is the mean of the four per-task means. A ratio above 1 means the first arm took
longer or cost more.

| comparison | scope | seconds | time ratio | cost | cost ratio | score |
|---|---|---|--:|---|--:|---|
| `opus/xhigh` vs `sonnet/medium` | all | 86.2 s vs 14.0 s | **6.2x** | $0.2923 vs $0.0441 | **6.6x** | 1.000 vs 1.000 |
| `opus/high` vs `sonnet/medium` | all | 41.7 s vs 14.0 s | **3.0x** | $0.1672 vs $0.0441 | **3.8x** | 1.000 vs 1.000 |
| `opus/high` vs `sonnet/high` | all | 41.7 s vs 21.6 s | **1.9x** | $0.1672 vs $0.0586 | **2.9x** | 1.000 vs 1.000 |
| `opus/medium` vs `sonnet/medium` | all | 22.0 s vs 14.0 s | **1.6x** | $0.1066 vs $0.0441 | **2.4x** | 1.000 vs 1.000 |
| `sonnet/high` vs `sonnet/medium` | all | 21.6 s vs 14.0 s | **1.5x** | $0.0586 vs $0.0441 | **1.3x** | 1.000 vs 1.000 |
| `sonnet/xhigh` vs `sonnet/medium` | all | 51.7 s vs 14.0 s | **3.7x** | $0.1086 vs $0.0441 | **2.5x** | 1.000 vs 1.000 |
| `sonnet/low` vs `sonnet/medium` | all | 12.8 s vs 14.0 s | **0.9x** | $0.0405 vs $0.0441 | **0.9x** | 0.998 vs 1.000 |
| `haiku/medium` vs `sonnet/medium` | all | 22.0 s vs 14.0 s | **1.6x** | $0.0046 vs $0.0441 | **0.1x** | 0.995 vs 1.000 |
| `haiku/low` vs `sonnet/medium` | all | 18.3 s vs 14.0 s | **1.3x** | $0.0041 vs $0.0441 | **0.1x** | 0.988 vs 1.000 |
| `haiku/xhigh` vs `haiku/low` | all | 64.0 s vs 18.3 s | **3.5x** | $0.0116 vs $0.0041 | **2.8x** | 1.000 vs 0.988 |
| `sonnet/xhigh` vs `opus/high` | all | 51.7 s vs 41.7 s | **1.2x** | $0.1086 vs $0.1672 | **0.6x** | 1.000 vs 1.000 |
| `haiku/xhigh` vs `haiku/low` | t1 | 31.8 s vs 12.9 s | **2.5x** | $0.0065 vs $0.0037 | **1.8x** | 1.000 vs 1.000 |
| `haiku/low` vs `sonnet/medium` | t1 | 12.9 s vs 8.9 s | **1.4x** | $0.0037 vs $0.0369 | **0.1x** | 1.000 vs 1.000 |
| `haiku/low` vs `sonnet/medium` | t2 | 10.7 s vs 11.9 s | **0.9x** | $0.0027 vs $0.0356 | **0.1x** | 0.960 vs 1.000 |
| `haiku/low` vs `sonnet/low` | t2 | 10.7 s vs 8.6 s | **1.2x** | $0.0027 vs $0.0321 | **0.1x** | 0.960 vs 1.000 |
| `opus/xhigh` vs `sonnet/medium` | t2 | 29.2 s vs 11.9 s | **2.5x** | $0.1502 vs $0.0356 | **4.2x** | 1.000 vs 1.000 |
| `opus/xhigh` vs `haiku/low` | t2 | 29.2 s vs 10.7 s | **2.7x** | $0.1502 vs $0.0027 | **55.6x** | 1.000 vs 0.960 |
| `sonnet/high` vs `sonnet/medium` | t3 | 27.5 s vs 16.6 s | **1.7x** | $0.0712 vs $0.0502 | **1.4x** | 1.000 vs 1.000 |
| `opus/high` vs `sonnet/medium` | t3 | 52.4 s vs 16.6 s | **3.2x** | $0.1987 vs $0.0502 | **4.0x** | 1.000 vs 1.000 |
| `haiku/medium` vs `sonnet/medium` | t3 | 33.9 s vs 16.6 s | **2.0x** | $0.0063 vs $0.0502 | **0.1x** | 1.000 vs 1.000 |
| `sonnet/high` vs `sonnet/medium` | t4 | 31.6 s vs 18.5 s | **1.7x** | $0.0720 vs $0.0537 | **1.3x** | 1.000 vs 1.000 |
| `opus/high` vs `sonnet/high` | t4 | 76.1 s vs 31.6 s | **2.4x** | $0.2475 vs $0.0720 | **3.4x** | 1.000 vs 1.000 |
| `opus/xhigh` vs `sonnet/medium` | t4 | 175.3 s vs 18.5 s | **9.5x** | $0.5126 vs $0.0537 | **9.5x** | 1.000 vs 1.000 |
| `haiku/low` vs `sonnet/medium` | t4 | 24.2 s vs 18.5 s | **1.3x** | $0.0050 vs $0.0537 | **0.1x** | 1.000 vs 1.000 |

Haiku's cost rows above round to "0.1x". Read the other way, so that the words in section
3's descriptions can be traced: on the transform task `sonnet/medium` cost **9.9x**
`haiku/low` ("a tenth"); on the extraction task `sonnet/medium` cost **13.2x** `haiku/low`
("a thirteenth") and `sonnet/low` **11.9x**; across all four tasks `sonnet/medium` cost
**9.5x** `haiku/medium` and **10.6x** `haiku/low`.

Ranges you may quote, each read off the grid:

- `xhigh` against `medium` on the same model: **2.9x** (Haiku), **3.7x** (Sonnet),
  **3.9x** (Opus) the time. `high` against `medium`: **1.4x**, **1.5x**, **1.9x**.
- `low` against `medium`: **17%**, **8%**, **9%** faster (Haiku, Sonnet, Opus).
- Haiku against Sonnet at `medium`: **1.6x** the time, **9.5x** cheaper, **3.1x** the
  output tokens.
- Measured effort multipliers, each model against its own `high`: the table in
  `RESULTS.md` under "Measured effort multipliers".
- Counts: on the extraction task Haiku at `low` got **48 of 50** answers, at `medium`
  **49 of 50**, at `high` and `xhigh` **100 of 100**; Sonnet **200 of 200**; Opus **200 of
  200**. On the review task Sonnet and Opus at `medium` and above found **330 of 330**
  defects; each model at `low` missed one hard defect once. In the whole sweep **3**
  answers and **3** defects were missed, and **1** defect was reported with a repro that
  asserted the wrong value.
- **47 of 48** task x arm cells scored 0.98 or better. The sweep billed **$18.86**.

What was **not** measured, and must not be claimed: tokens per second for any model; fast
mode; `max` effort; the advisor's latency or cost when consulted (it was attached to all
240 runs and called by none); any task with a blast radius, an unstated invariant or an
absence to prove; `judge` as a tier, on adjudication. (Its model-and-effort cell,
`opus/xhigh`, was measured on the four bounded tasks, and may be quoted as that cell.)

Fixture facts you may state: the transform task has 40 records; the extraction task asks
ten questions of a 2,400-line log; the implementation task has 42 hidden tests. Do not
state how many defects the review task seeds, or describe any of them: the sweep is meant
to be re-run, and those are its answers.

A 0.3.0 rule of thumb is retired and must not be carried over: "sample 5-10 tasks; below
roughly 70% first-pass acceptance, promote". Neither number has a source, and with a 20x
price gap the threshold is wrong — section 5's retry table is what now says how much
failure a cheap tier can carry. Keep the advice to sample your own work; drop the numbers.

## 7. Per-file instructions

**All files.** Apply sections 0-6. Resolve every `contradicted` and `stale-derived` finding
in your audit file; keep every `still-true-keep`; reframe every `needs-reframe` in a
clause, not a paragraph. Seven tiers become eight.

**Other files are being rewritten at the same time as yours.** Do not read another group's
file to learn a fact — it may be half-edited. This spec is the truth for anything shared.

**Keep every existing section heading** unless it is renamed here, because other files
cite them by name. The only renames, all in `references/model-selection.md`:

| was | is now |
|---|---|
| "The effort x model grid" | "The measured grid" |
| "The Haiku 200K context trap" | "The 100K price cliff" |
| "Haiku takes no effort setting" (bold lead-in) | "Haiku takes an effort setting" |

New sections: "Speed" in `SKILL.md`; a `scout` entry in `agent-catalog.md`. When you cite
another file, cite one of its existing headings or one named here.

**Counts you may need.** `hooks/test_tier_check.py` has **53** cases. `evals/evals.json`
will have **15** cases after this release and `evals/trigger-evals.json` **24** queries.
The audit behind `evals/audit-0.4.0/` was 18 agents and recorded 443 findings.

**`agents/*.md`** — the frontmatter of all eight files is already in place, generated
from section 3 and validated. **Do not edit any frontmatter.** Bodies only:
- `mechanical.md`: delete the paragraph beginning "There is deliberately no `effort:`
  here" outright, and replace it with two sentences: the tier pins `low`, and why
  (an unset effort inherits the session's; measured 2.5x slower at `xhigh`). Rewrite the
  `ToolSearch` and `omitClaudeMd` paragraphs on the mandate reason in section 3, not the
  200K wall. Keep the operating rules and the return-value contract.
- `scout.md` is new. Model it on `mechanical.md` and `inspector.md`: a short "why this
  tier exists" with its measured numbers from section 6, then operating rules, then the
  shared return-value contract. Its operating rules must include: **quote the evidence**
  — the line, with its line number or file — for every fact returned, so the caller can
  check it in seconds; **say "not found"** rather than guess; **re-read adjacency** — when
  a question is about the line before or after a match, print both lines and name which
  is which, because that is the shape this tier got wrong; do not edit anything; if the
  task turns out to need a verdict, stop and say so.
- `inspector.md`: now Sonnet at **medium**. Rewrite "Why this tier exists" around the
  measurement, including that it was saturated, and add the call-site `effort: 'high'`
  step before escalation. Replace the two "honest caveats" with what is now known:
  quality at `medium` against `high` was measured (equal, saturated); quality against the
  Opus tiers was measured on bounded work only (equal, saturated) and is still unmeasured
  on escalation-shaped work.
- `worker.md`, `drafter.md`, `reviewer.md`, `builder.md`, `judge.md`: replace every price
  ratio with the measured figure for that tier from section 6; change nothing else that
  the audit does not flag.

**`skills/delegate/SKILL.md`** — the load-bearing file. It is read into context every time
the skill fires, so it must not grow: the rewrite is to be **no longer than the 541 lines
it replaces**, and shorter is better. Cut all version-history narration.
- Frontmatter `description`: keep every trigger phrase that is there (they were measured
  to fire); correct the three false claims at the end — the Agent tool does take
  `effort`, Haiku does take an effort setting, and an omitted effort inherits the
  session's; add speed in agent-specific words only ("these agents are too slow", "make
  this fan-out faster") — a bare "too slow" would fire on any slow build.
- "If you are writing a Workflow script": an untiered call inherits model **and** effort.
  Stage table per section 3, with `scout` as one narrow row.
- The ten-second ladder: rule 4 names a tier — `inspector` for a read you will act on,
  `scout` when you can check the answer and cost matters — instead of "omit `model`",
  which now means the session's model at the session's effort. Rule 6 keeps only the
  validated `schema` as a reason a single item needs a Workflow; a specific effort no
  longer does, because `Agent` takes one.
- "Effort": rewrite around precedence, inheritance, the three places it is set, and the
  measured default (`medium`). The "reachable from a single Agent call" table collapses,
  since any model at any effort now is.
- "Model tier": re-based ladder; the two gates stay, the Haiku gate becomes the
  detectability gate; the 150K predicate goes; the retry table is section 5's.
- Add a short **"Speed"** section built from section 6: the levers in the order they paid.
- Anti-patterns: 3 and 4 rest on reversed facts and are rewritten; add "leaving effort
  unset" and "raising effort on bounded work".

**`references/model-selection.md`** — cost table, worked spend and break-evens from
section 5. Replace "The effort x model grid" with the measured grid and multipliers,
stating plainly that the index it used to cite described Sonnet 5 and Opus 5. Replace
"The Haiku 200K context trap" with a short section on the 100K price cliff. Rewrite "Two
things that break the table above": Haiku takes effort; the advisor section keeps its
mechanism and corrects the cache-read claim. "How to set each knob": the `Agent` row now
has effort, and add the precedence line. Keep "The tool surface is the biggest lever" and
add the 2.1.295 re-measurement beside the dated one. Keep the MCP section's mechanism and
its error table.

**`references/agent-catalog.md`** — eight tiers; `scout` gets a section; ratios from
section 6; the selection table gains the `scout` row and loses "400K of input -> worker
because of the 200K wall". Line 62 carries `mechanical`'s Tools bullet under `builder` —
a copy-paste bug the audit found; fix it.

**`references/workflow-patterns.md`** — the bare-opts table, the per-stage tiering table
and both sketches. `inspector` is medium; show `effort: 'high'` composed with `agentType`
once, as the way to raise one stage (this composition was exercised by all 240 sweep
runs). Replace the three "rules that override the table" that rest on the 200K wall and
the old ratios. The dated incident measurements stay exactly as they are.

**`README.md`** — "The constraint this plugin exists to solve" is rewritten: the
constraint is no longer that effort is unreachable, it is that an unpinned subagent
inherits the session's model and effort, and that only a definition can set `tools`,
`maxTurns` and `omitClaudeMd`. Eight-tier table with measured seconds and cost. Note that
an install may be a synced copy, which does not pick up working-tree edits (facts file).

**`evals/`** — `evals.json`: case 4 flips (the tool takes `effort` and it overrides the
definition, but a tier also brings tools, turns and rules); case 8 stays "no" for
ambiguity and because a 400-file job is a fan-out, not for a wall; case 2 drops the 200K
clause and routes by whether the answer will be checked. Add three cases: an unset effort
inheriting the session's; "use Haiku to make it faster" (it is cheaper, not faster); and
"my fan-out is slow" (effort first, then tier, then shape). `trigger-evals.json`: add at
least two speed-framed positives and one speed-framed negative that must not fire.
`evals/README.md`: correct the counts and the 200K sentence; the "measured results" rows
describe earlier descriptions and stay as dated history.

## 8. Things that are still true and must not be "corrected"

- `reviewer` and `builder` are `model: inherit`; in an Opus session they run Opus. Probed.
- The pinned tiers pin, and a pin is honoured: `drafter` Sonnet at `high`, `worker` and
  `inspector` Sonnet at `medium`, `judge` Opus at `xhigh`. (`inspector` pinned `high` in
  0.3.0, which is the definition probe row 3 ran; that row proves frontmatter effort is
  honoured, not that `inspector` is `high` today.)
- An `agent()` call with no `agentType` inherits the session model, and loses `maxTurns`,
  the tool allowlist, `omitClaudeMd`, the operating rules and the return-value contract.
- The tool surface is the biggest input lever. Re-measured on 2.1.295: all-tools
  `general-purpose` billed 38,112 and 38,131 subagent tokens for a one-line echo against
  6,824-8,869 for the scoped tiers — 4.3-5.6x. The 2026-09-30 paired run (98k vs 435k,
  4.4x) stands as a dated measurement beside it.
- Caches are model-scoped; a multi-model cascade forfeits cache reuse.
- The advisor attaches to every subagent, `mechanical` included; here it resolved to
  `claude-fable-5-1`. It cannot be suppressed per agent. Controls are session-wide.
- `disallowedTools` is ignored when `tools:` is set.
- Every dated incident measurement (2026-09-30 x2, 2026-10-08) and every `maxTurns`
  derivation. Those ran on `claude-opus-5`; say so where a reader might take the model id
  as current, and change nothing else.
- The hook's behaviour: denies an `agent()` with no `agentType`, fails open, one waiver.
- `SKILL.md` frontmatter `effort:` sets the invoking turn, never a subagent.
- Fable is still not offered as a tier, for the same structural reasons.
- `pipeline()` vs `parallel()`, isolation, the concurrency cap, the return-value contract,
  the delegation floor formula `savings = D - (S + C + B + 2R)`.
