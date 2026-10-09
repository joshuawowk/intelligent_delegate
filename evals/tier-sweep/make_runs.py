#!/usr/bin/env python3
"""Lay out one working directory per sweep run and print the Workflow `args`.

    python3 make_runs.py <root> [--pilot] [--reps N]  > args.json

Each run gets a private copy of its task's fixture directory at <root>/<run_id>/work, so
runs that write files cannot collide. <root> must be OUTSIDE this repository: workflow
subagents start with the repo as their working directory, and a run directory beneath
it would put the answer keys one `ls ..` away.

Run order is shuffled with a fixed seed so that drift in API latency over the length of
the sweep lands on every arm equally instead of on whichever arm happened to run last.
"""
import json
import os
import random
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# task -> the shipped definition whose tool surface, system prompt and maxTurns the run
# borrows. Model and effort are overridden per arm; holding the definition fixed within
# a task is what makes arms comparable.
TASK_AGENT = {
    "t1": "intelligent-delegate:worker",     # writes a file
    "t2": "intelligent-delegate:inspector",  # read-only extraction
    "t3": "intelligent-delegate:inspector",  # read-only review
    "t4": "intelligent-delegate:worker",     # writes a file
}
# Every effort the shipped tiers use, on every model family a tier can resolve to. `max`
# is left out: no tier pins it, and it is reachable only through a waiver.
ARMS = [(m, e) for m in ("haiku", "sonnet", "opus") for e in ("low", "medium", "high", "xhigh")]
# A smoke test of the review task across the three families, run before the sweep.
PILOT = [("t3", "haiku", "low"), ("t3", "sonnet", "medium"), ("t3", "opus", "medium")]
REPS = 5


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = os.path.abspath(argv[1])
    pilot = "--pilot" in argv
    reps = int(argv[argv.index("--reps") + 1]) if "--reps" in argv else REPS
    if os.path.commonpath([root, os.path.dirname(os.path.dirname(HERE))]) == os.path.dirname(os.path.dirname(HERE)):
        sys.exit("refusing: <root> is inside the repository — see the docstring")
    runs = []
    if pilot:
        for task, model, effort in PILOT:
            runs.append((task, model, effort, 1))
    else:
        for task in ("t1", "t2", "t3", "t4"):
            for model, effort in ARMS:
                for rep in range(1, reps + 1):
                    runs.append((task, model, effort, rep))
        random.Random(20261009).shuffle(runs)
    os.makedirs(root, exist_ok=True)
    out = []
    for task, model, effort, rep in runs:
        rid = "%s-%s-%s-%d" % (task, model, effort, rep)
        # <root>/<run_id>/work — nested so that a run's parent directory holds nothing but
        # its own work dir. Flat siblings would put another arm's finished output.jsonl or
        # solution.py one `ls ..` away.
        if os.path.isdir(os.path.join(root, rid)):
            shutil.rmtree(os.path.join(root, rid))
        d = os.path.join(root, rid, "work")
        shutil.copytree(os.path.join(HERE, "fixtures", task), d)
        out.append({"id": rid, "task": task, "model": model, "effort": effort, "rep": rep,
                    "dir": d, "agentType": TASK_AGENT[task]})
    with open(os.path.join(HERE, "briefs.json")) as fh:
        briefs = json.load(fh)
    json.dump({"root": root, "briefs": briefs, "runs": out}, sys.stdout)
    sys.stderr.write("%d runs laid out under %s\n" % (len(out), root))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
