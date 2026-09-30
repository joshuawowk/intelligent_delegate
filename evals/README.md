# evals

Two suites. They look similar and answer different questions.

| File | Schema | Question | Size |
|---|---|---|---|
| `evals.json` | skill-creator behavioural grading — `skill_name`, `evals[]` of `id` / `prompt` / `expected_output` / `expectations` | Once the skill is loaded, does it **route correctly**? | 8 cases, 24 expectations |
| `trigger-evals.json` | flat list of `{query, should_trigger}` | Does the skill **fire at all**? | 16 queries — 10 positive, 6 adversarial negatives |

**A skill can pass one and fail the other, in both directions.** A sharp description
with a muddled body triggers reliably and then gives the wrong answer — full marks on
`trigger-evals.json`, failures across `evals.json`. A correct body behind a narrow
description passes every routing case when you invoke it by hand as
`/intelligent_delegate:delegate`, and never fires on its own, which is the only way it
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

The `expectations` here are deliberately adversarial about *reasoning*, not just the
verdict — case 2 wants the volume-vs-tool-call distinction stated, case 3 wants the
negative-claim predicate named, case 8 wants Haiku's 200K window cited as a wall rather
than as a cost. A case that lands the right answer for the wrong reason should fail.

## Running `trigger-evals.json`

```bash
cd ~/.claude/plugins/marketplaces/claude-plugins-official/plugins/skill-creator/skills/skill-creator
python3 -m scripts.run_eval \
  --eval-set /path/to/intelligent_delegate/evals/trigger-evals.json \
  --skill-path /path/to/intelligent_delegate/skills/delegate \
  --runs-per-query 2 --verbose
```

`--model` defaults to your configured session model; pass it explicitly if you want the
trigger rate to match a specific one. `scripts.run_loop` wraps the same
`--eval-set` / `--skill-path` / `--model` (required there, not optional) in a
description-rewriting loop — add `--max-iterations`; it holds out 40% and selects on the
held-out score.

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
levels. In that vocabulary "haiku" is a model name, so **"write me a haiku about autumn
leaves"** is a live false-trigger risk on a lexical collision alone. The other five
negatives target the description's broad cost vocabulary — it invites any turn where
something feels slow or expensive — which is subjective enough to match almost any
ordinary task. (The v1 clause they were originally written against, *"when work feels
too expensive, too slow, or too token-hungry"*, was rewritten in v2; the negatives still
probe the same risk.) A CSS fix, a rename, a regex, a `git rebase` explanation, a new CLI flag: all
plausible work, none of them wanting a routing decision.

Over-triggering is a real cost, not a tidiness complaint. The plugin is ~1,016 tokens
always-on, but the `delegate` skill costs ~5.1k more every time it fires. A skill that
loads on CSS padding taxes every unrelated turn for the length of the session, and the
tax is invisible — nobody attributes a slow, expensive turn to a skill that had nothing
to do with it. A description tuned only for recall is a worse artifact than a narrow
one.

## Measured results

Run with `evals/measure_triggers.py`, which drives the **installed** plugin rather than a
stub. **It defaults to n=3 per query** — see the warning below for why n=1 is not a
measurement. A query counts as firing if it fires in at least half its runs.

| description | recall (should fire) | false positives (should not) |
|---|--:|--:|
| v1 — capability phrasing | 2/10 *(n=1)* | 0/6 |
| v2 — explicit short-form phrasings + "do not answer from memory" | 7–8/10 *(n=1)* | 0/6 |
| current — same, with the advisor claim made conditional | **~9/10** *(n=3 on contested queries)* | 0/6 |

**Single-run numbers on this harness are noise-dominated. Do not quote them.** Two
consecutive n=1 runs of the current description scored 8/10 and 7/10, which looked like a
regression caused by rewording. It was not. Re-running the three apparent misses at n=3:

| query | n=1 | n=3 |
|---|---|---|
| "I want to fan this out across 30 files in parallel" | missed | **3/3 fired** |
| "Should I spawn a subagent for this or just do it inline?" | missed | **2/3 fired** |
| "Is it worth spinning up agents for this, or is the overhead not worth it?" | missed | **0/3 — genuine** |
| *control:* "Which model should I use for these worker agents?" | fired | 3/3 ✓ |

Two of the three "misses" fire reliably or usually; only one is a stable miss. The
apparent 8→7 regression was a coin flip, and acting on it would have meant tuning a
description against sampling noise. Always include a known-firing control so a systemic
failure — auth, a broken install, a harness bug — is distinguishable from a real miss.

**The one stable miss** is *"is it worth spinning up agents for this, or is the overhead
not worth it?"*, whose phrasing appears near-verbatim in the description. It is not a
lexical gap: it reads as asking for a judgement rather than for reference material, and
the model answers it directly. Chasing it risks the false-positive column, which is
clean across every run. Over-triggering is the more expensive failure — a skill that
loads on unrelated turns taxes every one of them.

Raw per-query output from the most recent full run is in `last-trigger-run.json`.
