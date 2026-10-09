# evals

Two suites. They look similar and answer different questions.

| File | Schema | Question | Size |
|---|---|---|---|
| `evals.json` | skill-creator behavioural grading — `skill_name`, `evals[]` of `id` / `prompt` / `expected_output` / `expectations` | Once the skill is loaded, does it **route correctly**? | 15 cases |
| `trigger-evals.json` | flat list of `{query, should_trigger}` | Does the skill **fire at all**? | 24 queries — positives, adversarial negatives and controls |

**A skill can pass one and fail the other, in both directions.** A sharp description
with a muddled body triggers reliably and then gives the wrong answer — full marks on
`trigger-evals.json`, failures across `evals.json`. A correct body behind a narrow
description passes every routing case when you invoke it by hand as
`/intelligent-delegate:delegate`, and never fires on its own, which is the only way it
would ever have been used. Run both.

## Running `evals.json`

There is no one-liner. This is the skill-creator procedure and it is subagent-driven:

1. For each case, spawn two subagents in the same turn — one pointed at
   `skills/delegate/`, one baseline with no skill — and save outputs to
   `<workspace>/iteration-N/eval-<id>/with_skill/` and `without_skill/`.
2. Grade each run against that case's `expectations` with a grader subagent reading
   `agents/grader.md` from the skill-creator skill. `grading.json` must use the fields
   `text`, `passed`, `evidence` — the viewer depends on those exact names.
3. Aggregate and view, from the skill-creator directory:

```bash
cd ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator
python3 -m scripts.aggregate_benchmark <workspace>/iteration-N --skill-name delegate
python3 eval-viewer/generate_review.py <workspace>/iteration-N \
  --skill-name delegate --benchmark <workspace>/iteration-N/benchmark.json
```

### The 0.4.0 run, and a second route

`evals/behavioural.workflow.js` runs the cases through the Workflow tool instead: an agent
on the session model reads `skills/delegate/SKILL.md` cold and answers the prompt as the
main loop would, and a second grades the answer against that case's `expectations`, one
pass/fail with quoted evidence per line. Three runs per case. It has no no-skill baseline
arm, so it says whether the skill routes correctly, not whether it beats having none.

| run, 2026-10-09 | skill at | cases passing in all 3 runs | runs passing every expectation | expectation checks |
|---|---|:--:|:--:|:--:|
| 1 — all 15 | `286f34c` | 10 / 15 | 30 / 45 | 173 / 192 |
| 2 — the five revised cases | between the two | 4 / 5 | 14 / 15 | 74 / 75 |
| **3 — all 15, final text** | `0ca95cf` | **11 / 15** | **39 / 45** | **185 / 192** |

Every graded check, with its quoted evidence, is in `behavioural-runs-2026-10-09.json`
(answers kept for run 3). No answer in any run opened anything but the skill: every answering agent's tool calls
were checked for `evals/`, `docs/`, `README.md` and `CHANGELOG.md`, and none read the
reference files either — the skill body was enough for all fifteen. That check was run by
the author against transcripts that are not in this repository; it is a claim here, not
something you can re-derive.

**What changed between run 1 and the later runs — said in full, because loosening a test
until it passes looks exactly like this.** In run 1 five cases passed in no run. Seven
expectation lines were rewritten because of it, in those five cases:

| case, line | run 1 | what it demanded | what it grades now |
|---|:--:|---|---|
| 2, routing | 0 / 3 | also say when `scout` *would* do | the route: `inspector`, with `scout` rejected or conditioned |
| 4, what a tier brings | 0 / 3 | name all five things | name at least one |
| 14, why Haiku is slower | 0 / 3 | give the reason | the reason is right if one is given |
| 13, precedence | 1 / 3 | the three-step chain spelled out | call-site overrides the definition |
| 13, quantifying | 1 / 3 | one specific figure, with its task | any of three listed figures, or none |
| 14, when Haiku is allowed | 1 / 3 | "parallelism hides the latency" | a cost choice, where a miss is detectable |
| 5, the tier | 0 / 3 | `builder` | resolve the ambiguity first, then a stated tier per reading |

The first six are the rubric asking for a recital where the route was right: case 2's
answers all sent the changelog read to `inspector` and turned `scout` down because a
missed entry is silent, and failed for not also saying when `scout` would do. **Three of
those six had failed in only two runs of three**, not all three, and were loosened all the
same — the weakest part of this account, and the reason each rewritten line was then
checked for whether it still fails a wrong answer. A reviewer-tier pass built a plausible
wrong answer for each: cases 2, 4 and 14 still caught theirs. Case 5's did not, and one of
case 13's could not be checked by a grader that reads only the rubric; both were tightened
again (case 5 now names the tier each reading must get and fails a straight-to-`builder`
answer; case 13 lists the only figures it accepts).

The seventh was the skill. Case 5 expected `builder` for twelve boards needing "the same
edit", because two readings survive. The skill also says not to fan an inherit tier across
items. All three answers did something better than either rule — settle which reading is
meant, then tier by the answer — and the skill now says that, with the case where the
ambiguity cannot be settled named as the exception.

**Reading run 3.** None of its seven failed checks is a wrong route. Each is an answer of
about 350 words leaving out a supporting point: a cost ratio given without saying it was
the measured one, the waiver offered without its condition. And one is a warning about
the method: case 11 passed 3/3 in run 1 and 1/3 in run 3 with no change to the text it
draws on. At n=3 one borderline rubric line moves a case two places. Treat a single case's
score as noise and the totals as the signal, and do not tune the skill to a line.

**Limits.** The grader is a model — the one place in this release where a model's judgment
is the measurement; the harness caps answers near 350 words, which is what several misses
were; and the stand-in reads the skill in a subagent, where a real main loop has it loaded.

The `expectations` here are deliberately adversarial about *reasoning*, not just the
verdict — case 2 wants the volume-vs-tool-call distinction stated and the tier routed by
whether the answer will be checked, case 3 the negative-claim predicate, case 4 call-site
`effort` confirmed *and* why a tier still beats a bare call, case 8 ambiguity and fan-out
as the reasons, not a context wall. Cases 13-15: effort inheritance, "Haiku to go faster"
(cheaper, not faster), a slow fan-out (effort, then tier, then shape). A case that lands
the right answer for the wrong reason should fail.

## Running `trigger-evals.json`

```bash
cd ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator
python3 -m scripts.run_eval \
  --eval-set /path/to/intelligent_delegate/evals/trigger-evals.json \
  --skill-path /path/to/intelligent_delegate/skills/delegate \
  --runs-per-query 2 --verbose
```

`--model` defaults to your configured session model; pass it to match a specific one.
`scripts.run_loop` wraps the same `--eval-set` / `--skill-path` / `--model` (required
there) in a description-rewriting loop — add `--max-iterations`; it holds out 40% and
selects on the held-out score.

> **`run_eval.py` does not test the installed skill.** It parses `description:` out of
> `SKILL.md` and writes a throwaway slash-command into `<project_root>/.claude/commands/`
> whose entire body is `This skill handles: <description>`, runs `claude -p <query>`
> against it, then deletes it in a `finally`. Nothing else from the skill is present.
> Because the stub carries no useful content, Claude usually just answers the question
> itself rather than invoking it — measured here, the stub scored **0 triggers across 32
> runs** (16 queries × `--runs-per-query 2`), while the *real* installed plugin did fire
> on explicit delegation queries in the same environment.
>
> Treat a `run_eval.py` score as a measurement of **the description text in isolation**,
> useful for comparing one description against another, and never as evidence that the
> skill is broken. Verify against the installed plugin before acting on a low score.
>
> One more trap: `project_root` is found by walking up from **cwd** looking for a
> `.claude/` directory. Invoked as a module from the skill-creator directory, as above,
> cwd is already under `~/.claude/plugins/`, so the first parent holding a `.claude/` is
> your home directory — the stub lands in `~/.claude/commands/` and the child
> `claude -p` runs with `$HOME` as its cwd, not this repo.

## `claude plugin eval`

The first-party route, and the one to prefer for anything that must be reproducible:

```bash
claude plugin eval . --ablation with-without
```

It does **not** read either file here. It discovers cases as `evals/**/case.yaml`, or
`prompt.md` plus `graders/*.md`, so against this directory as laid out it finds zero
cases. Porting `evals.json` into that layout is the obvious future move — it gets you a
no-plugin baseline arm and a `tool_used: Skill` grader for free, which is exactly the
two-suites-in-one thing this directory currently does by hand.

## Why the negatives are adversarial

The `delegate` description talks about model tiers, cheaper models, and reasoning effort
levels. In that vocabulary "haiku" is a model name (`haiku` still resolves to a model), so
**"write me a haiku about autumn leaves"** is a live false-trigger risk on a lexical
collision alone. The next five negatives target the description's broad cost vocabulary —
it invites any turn where something feels slow or expensive — which is subjective enough
to match almost any ordinary task. (The v1 clause they were originally written against,
*"when work feels too expensive, too slow, or too token-hungry"*, was rewritten in v2; the
negatives still probe the same risk.) A CSS fix, a rename, a regex, a `git rebase`
explanation, a new CLI flag: all plausible work, none of them wanting a routing decision.
The last, **"my webpack build is too slow"**, is the speed-framed negative: the description
names speed only in agent-specific words, because a bare "too slow" would fire on any slow
build. The speed positives pair with it, so matching "slow" alone cannot pass.

Over-triggering is a real cost, not a tidiness complaint. The `delegate` skill body loads in
full every time it fires, so a skill that loads on CSS padding taxes every unrelated turn
for the length of the session, and the tax is invisible — nobody attributes a slow,
expensive turn to a skill that had nothing to do with it. A description tuned only for
recall is a worse artifact than a narrow one.

## Measured results

Run with `evals/measure_triggers.py`, which drives the plugin itself rather than a stub —
loaded from this checkout with `--plugin-dir`, and confirmed from each session's own init
event. **It defaults to n=3 per query** — see the warning below for why n=1 is not a
measurement. A query counts as firing if it fires in more than half its runs.

| description | recall (should fire) | false positives (should not) | n |
|---|--:|--:|:--:|
| v1 — capability phrasing | 2/10 | 0/6 | 1 |
| v2 — explicit short-form phrasings + "do not answer from memory" | 7–8/10 | 0/6 | 1 |
| 2026-10-01 — same, with the advisor claim made conditional | **9/9 measured** | **0/6** | **3** |
| **0.4.0** (2026-10-09) — speed phrasings, effort and Haiku corrections, quoted YAML | **16/16** | **0/8** | **3** |

The **0.4.0** row is one real run on 2026-10-09 at `286f34c`, archived in
`last-trigger-run.json`: 24 queries at n=3, `TP=16 FN=0 FP=0 TN=8 ERROR=0`. Every positive
fired 3/3 and every negative 0/3, both controls included, and all 72 calls were confirmed
by their own init event to have loaded the plugin from this checkout. It covers the two
speed-framed positives added in this release and the speed-framed negative ("My webpack
build is too slow…") that has to stay silent now that the description mentions speed. It
is one run: the rows above it show what a single run on this suite has been worth before.

The 2026-10-01 row is a single real run of all 18 cases at n=3 against the plugin as then
installed: `TP=10 FN=0 FP=0 TN=7 ERROR=1`. It was the content of `last-trigger-run.json`
until `0ca95cf` replaced it with the 0.4.0 run; read it with
`git show 286f34c:evals/last-trigger-run.json`. It measured a description since rewritten,
on a suite six queries smaller than today's. Reading that run honestly:

- **Nine of the ten non-control positives were fully measured and all fired** — eight at 3/3,
  one at 2/3. The tenth ("this is burning way too many tokens…") **errored on a 300s
  timeout** and is excluded from the denominator rather than counted as a miss; it fired on
  the one run of it that did complete, so treat it as unmeasured, not as a regression.
- **All six non-control negatives fired 0/3.** The false-positive column is still clean, now
  at n=3 rather than n=1.
- **Both control cases behaved**: the must-fire control 3/3, the must-not-fire control 0/3.
  That is what makes the rest of the numbers worth reading at all.
- The only skill id observed anywhere in the run was `intelligent-delegate:delegate`.

The v1 and v2 rows remain n=1, kept only to show the direction of travel; they are not
comparable to the n=3 row.

**Single-run numbers on this harness are noise-dominated. Do not quote them.** Two
consecutive n=1 runs of the then-current description scored 8/10 and 7/10, which looked
like a regression caused by rewording. It was not. Re-running the three apparent misses at n=3:

| query | n=1 | n=3 |
|---|---|---|
| "I want to fan this out across 30 files in parallel" | missed | **3/3 fired** |
| "Should I spawn a subagent for this or just do it inline?" | missed | **2/3 fired** |
| "Is it worth spinning up agents for this, or is the overhead not worth it?" | missed | **0/3 — genuine** |
| *control:* "Which model should I use for these worker agents?" | fired | 3/3 ✓ |

The apparent 8→7 regression was a coin flip; acting on it would have meant tuning a
description against sampling noise. Always include a known-firing control so a systemic
failure — auth, a broken install, a harness bug — is distinguishable from a real miss.
`trigger-evals.json` ships two, flagged `"control": true`: a must-fire query and a
must-not-fire query, both passed in the archived run (3/3 and 0/3). The harness prints
`CONTROL CASE FAILED` when one breaks, because that invalidates every other number in the run.

**The "one stable miss" is no longer a miss.** *"Is it worth spinning up agents for this, or
is the overhead not worth it?"* was explained at length as a stable 0/3 failure. At n=3
against the 2026-10-01 description it fires **3/3**; the earlier 0/3 was noise or an unattributed
description change. A confident explanation sat on a number that did not survive
re-measurement, twice on this suite. **Re-measure before explaining.** Over-triggering remains
the more expensive failure, so the clean false-positive column is the one to protect.

**Provenance of `last-trigger-run.json`.** The 2026-10-09 run of the 0.4.0 description: 24
queries at n=3, with its own `generated_utc`, `runs_per_query`, `head`, `dirty`,
`loaded_from`, `calls_confirmed`, `calls_unconfirmed`, `skill_id` and totals. There is no
`installed_sha` any more: the harness stopped asking the install what it is and asks each
session what it loaded. Regenerating costs billed `claude -p` calls — one per query per run
— so re-run it when the description changes, not routinely. A run is archived unless
*every* case errored; errored cases stay visible as `state: "ERROR"` and are excluded from
the totals.

**Timeouts are the main source of noise, and they are not misses.** At 150s with 6-way
concurrency, 7 of 18 calls timed out; at 300s with 4-way, 1 of 18 did. The defaults are now
300s and concurrency 4 (`--timeout` / `--concurrency` are tunable). A timed-out case is an
`ERROR`, left out of the denominator: counting it as a miss misreads a slow API as a regression.

**What the harness now refuses to do.** Earlier versions never read `claude`'s exit status,
so a broken install — expired auth, a missing binary, a `stream-json` shape change — scored
`TP=0 FN=10 FP=0 TN=6` and exited **0**, reproducing a clean false-positive column while
measuring nothing. It now distinguishes an `ERROR` case from a miss and exits non-zero on
any error or mismatch.

**And it no longer takes the install's word for what it measured.** Every call passes
`--plugin-dir <this repo>`; each session's init event is read for the path it loaded the
plugin from; a call that loaded any other copy is an `ERROR`, and the run reports how many
calls were confirmed. Until 0.4.0 the script printed "measuring the WORKING TREE" on the
strength of a 2026-10-01 probe of a local-path install. On a machine where the plugin is a
synced copy (`claude plugin list` shows `@synced`) that sentence was false, nothing tested
it, and the run would have reported a clean measurement of the previous release. A line
the script prints is not a check the script performs.
