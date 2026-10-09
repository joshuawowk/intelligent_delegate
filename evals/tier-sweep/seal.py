#!/usr/bin/env python3
"""Move the answer keys out of the repository for the length of a sweep, and back.

    python3 seal.py hide <dir-outside-the-repo>
    python3 seal.py restore <dir-outside-the-repo>

Workflow subagents start with this repository as their working directory. A recursive
search issued without a path — the ordinary accident, not cheating — therefore walks
keys/ and src/ and returns matching lines from the reference implementations. analyze.py
detects that and voids the run, but a voided run is a lost data point; sealing removes
the route so there is nothing to detect.

`restore` puts everything back. `git status` is clean again afterwards, which is the
check that it worked.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# RESULTS.md and results/ are answers too: they name defects the review task seeds, and
# the sweep is meant to be re-run with them out of reach.
PRIVATE = ["keys", "src", "build_fixtures.py", "analyze.py", "test_graders.py",
           "RESULTS.md", "results", "results_md.py"]


def main(argv):
    if len(argv) != 3 or argv[1] not in ("hide", "restore"):
        print(__doc__)
        return 2
    vault = os.path.abspath(argv[2])
    repo = os.path.dirname(os.path.dirname(HERE))
    if os.path.commonpath([vault, repo]) == repo:
        sys.exit("refusing: the vault must be outside the repository")
    os.makedirs(vault, exist_ok=True)
    src, dst = (HERE, vault) if argv[1] == "hide" else (vault, HERE)
    moved = []
    for name in PRIVATE:
        a, b = os.path.join(src, name), os.path.join(dst, name)
        if not os.path.exists(a):
            continue
        if os.path.exists(b):
            sys.exit("refusing: %s already exists at the destination" % b)
        shutil.move(a, b)
        moved.append(name)
    print("%s: %s" % (argv[1], ", ".join(moved) or "nothing to move"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
