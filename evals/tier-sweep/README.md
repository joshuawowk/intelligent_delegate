# tier-sweep

Measures what a model × effort cell is actually worth — seconds, dollars and graded
quality — on four task shapes this plugin's tiers are routed. It exists because 0.3.0
set its tier defaults from a price sheet and an effort index, and neither says whether a
cheaper cell does the work.

`RESULTS.md` is the output. `DECISIONS.md` is how each result was allowed to move a tier
default, and it was committed before the sweep ran. Read both before quoting a number.

## What is run

| task | shape | graded by |
|---|---|---|
| t1 transform | 40 records, converted by rule and worked example | JSON equality, value and type, per record |
| t2 extract | ten questions over a 2,400-line log | exact match |
| t3 review | a module checked against a numbered spec | **running each finding's repro** |
| t4 implement | three functions from a spec | hidden tests |

Twelve arms — `haiku`, `sonnet`, `opus` at `low`, `medium`, `high`, `xhigh` — five reps
each, 240 runs. Each run borrows a shipped definition for its tool surface and overrides
only model and effort, so two arms of one task differ in nothing else. Run order is a
fixed-seed shuffle, so latency drift over the sweep lands on every arm equally.

No grader reads prose and none consults a model. The review task is the one where that
took work: a finding there is credited only if the repro it carries passes on a correct
ledger and fails on the reference-plus-one-defect variant for a seeded defect. Two
earlier graders for it were broken by adversarial review before the sweep ran, and
`test_graders.py` keeps every demonstrated exploit as a regression test.

## What is read from where

Nothing is taken from an agent's account of itself. Model and effort come from the
`requestedModel` and `effort` fields the harness writes on each assistant record; tokens
from per-request `usage`, priced at the rates in `../facts-2026-10-09.md`; duration is
last transcript record minus first.

A run is **void** when it ran at a model or effort other than its arm, consulted the
advisor, or had an answer in front of it — a private file's path, the key canary, or
another run's directory, in any tool call or tool result. Voids are listed with the
reason and excluded. Nothing is excluded silently.

## Running it

```bash
python3 build_fixtures.py              # deterministic; fails if a question's premise does not hold
python3 test_graders.py                # the graders' regression tests
python3 make_workflow.py               # sweep.workflow.js, with the briefs embedded
python3 make_runs.py <root> > args.json        # <root> must be OUTSIDE this repository
python3 seal.py hide <vault>           # move the answer keys out of the tree
#   ... run sweep.workflow.js through the Workflow tool with {"root": "<root>"} ...
python3 seal.py restore <vault>
python3 analyze.py <workflow-transcript-dir> args.json --vault <vault> --json results/raw.json
```

**Seal before you run.** Workflow subagents start with this repository as their working
directory. A recursive search issued without a path walks `keys/` and `src/` and returns
lines from the reference implementations. `analyze.py` detects that and voids the run,
but a voided run is a lost data point; `seal.py` removes the route. `git status` is clean
again after `restore`, which is the check that it worked.

`make_runs.py` refuses a `<root>` inside the repository, and nests each run at
`<root>/<run_id>/work` so that a run's parent directory holds nothing but its own work —
flat siblings put another arm's finished answer one `ls ..` away.

It bills 240 agent runs. A full sweep took about half an hour at six-way concurrency.

## What it cannot tell you

- **It is small.** Five reps, four tasks, one session, one day. A difference of a few
  hundredths between two cells is not a finding.
- **The tasks are synthetic and bounded.** Each has a checkable right answer, which is
  what makes it gradeable and also what makes it unlike the work an escalation tier is
  for. Nothing here has a blast radius, an unstated invariant or an absence to prove.
- **A saturated task ranks nothing.** Where every arm being compared scores at the
  ceiling, the sweep shows the cheaper cell is enough for work of that difficulty and
  shows nothing about harder work. `RESULTS.md` says so wherever it applies.
- **Latency is this session's.** Seconds include queueing behind five other agents and
  whatever the API was doing that half hour. Read ratios between arms, not absolutes.
- **Your workload is not this one.** The protocol in `SKILL.md` still applies: sample
  five to ten of your own tasks at the tier you are considering and count first-pass
  acceptance.
