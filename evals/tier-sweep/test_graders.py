#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key
"""Regression tests for the graders. Run: python3 test_graders.py

Every case under "exploit" is a way the first version of analyze.py was wrong, found by
an adversarial review of the fixtures before the sweep ran and reproduced here. They are
kept because each was a working repro, not a theory: a recall-only review grader paid
full marks for one guess per spec clause; a proximity rule credited a false finding that
happened to sit beside a seeded one; a hidden test demanded behaviour the spec did not
state; the module loader zeroed a correct solution; and a partial read of a key file
went undetected because the canary is only on its first line.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("analyze", os.path.join(HERE, "analyze.py"))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

KEYS = A.load_keys()
BUGS = KEYS["t3"]
FAILED = []


def check(name, got, want, cmp="eq"):
    ok = (got == want) if cmp == "eq" else (got < want)
    print("  %s %-66s %s" % ("ok  " if ok else "FAIL", name, "" if ok else "got %r, want %s %r" % (got, cmp, want)))
    if not ok:
        FAILED.append(name)


def main():
    d = tempfile.mkdtemp()
    run = {"dir": d}
    g3 = lambda fs: A.grade_t3(run, {"findings": fs}, KEYS)[0]
    spans = KEYS["t3_spans"]
    span = lambda ln: [n for n, a, b in spans if a <= ln <= b][0]
    start = {n: a for n, a, b in spans}
    real = [{"line": b["line"], "clause": b["clause"], "description": b["desc"]} for b in BUGS]

    print("t3 exploit: reports that understood nothing must score 0")
    check("one guess per public method at its def line",
          g3([{"line": l, "clause": c, "description": "this method violates the clause"}
              for l, c in [(38, 1), (44, 2), (55, 3), (66, 4), (72, 5), (82, 6), (87, 7), (95, 8), (109, 9), (133, 10)]]), 0.0)
    check("35 findings on every 4th line", g3([{"line": l, "clause": 0, "description": "bug"} for l in range(1, 140, 4)]), 0.0)
    check("one finding per line", g3([{"line": l, "clause": 0, "description": "bug"} for l in range(1, 140)]), 0.0)
    check("a false finding beside a seeded one",
          g3([{"line": 47, "clause": 2, "description": "the ValueError check is in the wrong order"}]), 0.0)
    check("right line, wrong clause, on all eight",
          g3([dict(f, clause=99) for f in real]), 0.0)
    check("no findings at all", g3([]), 0.0)

    print("t3: real findings must still be credited")
    check("exact line, right clause, real description", g3(real), 1.0)
    check("def line, right clause, real description",
          g3([dict(f, line=start[span(f["line"])]) for f in real]), 1.0)
    b5 = [b for b in BUGS if b["id"] == "B5"][0]
    deco = start[span(b5["line"])]
    check("a finding cited at the decorator above price_total",
          A.grade_t3(run, {"findings": [{"line": deco, "clause": 8, "description": "discount is truncated, not rounded half up"}]}, KEYS)[1]["found"], ["B5"])
    pad = real + [{"line": 3, "clause": 1, "description": "speculative concern %d" % i} for i in range(8)]
    check("padding costs: 8 real + 8 guesses scores below 8 real", g3(pad), 1.0, "lt")
    n = len(BUGS)
    check("...and by the expected amount (R 1.0, P n/(n+8))", round(g3(pad), 4), round(2 * n / (2 * n + 8), 4))

    print("t3: two defects in one function, and one finding that could be either")
    by = {b["id"]: b for b in BUGS}
    f7 = {"line": by["B7"]["line"], "clause": 7, "description": "limit=0 is falsy so everything is returned"}
    f11 = {"line": by["B11"]["line"], "clause": 7, "description": "returns the internal dicts, not copies"}
    check("both history defects reported -> both credited",
          A.grade_t3(run, {"findings": [f7, f11]}, KEYS)[1]["found"], ["B7", "B11"])
    both = {"line": by["B7"]["line"], "clause": 7, "description": "limit=0 returns everything, and the events are not copies"}
    check("one finding describing both credits exactly one",
          len(A.grade_t3(run, {"findings": [both]}, KEYS)[1]["found"]), 1)
    check("...and a second finding then picks up the other",
          A.grade_t3(run, {"findings": [both, f11]}, KEYS)[1]["found"], ["B7", "B11"])
    add_line = start["add_stock"] + 1
    check("the bool defect reported against add_stock, clause 1",
          A.grade_t3(run, {"findings": [{"line": add_line, "clause": 1, "description": "True is accepted because bool is an int"}]}, KEYS)[1]["found"], ["B9"])
    rm = by["B1"]["line"]
    check("bool defect and the >= defect both reported in remove_stock",
          A.grade_t3(run, {"findings": [
              {"line": rm, "clause": 2, "description": "uses >= so removing exactly the available units fails"},
              {"line": rm - 2, "clause": 2, "description": "a bool quantity such as True passes validation"}]}, KEYS)[1]["found"], ["B1", "B9"])
    check("the bool defect with a clause it does not violate is not credited",
          A.grade_t3(run, {"findings": [{"line": add_line, "clause": 9, "description": "bool accepted"}]}, KEYS)[1]["found"], [])
    check("merge defect needs the right substance, not just the function",
          A.grade_t3(run, {"findings": [{"line": by["B10"]["line"], "clause": 10, "description": "merge is slow for large inventories"}]}, KEYS)[1]["found"], [])

    print("t1: types and order")
    exp = KEYS["t1"]
    out = os.path.join(d, "output.jsonl")
    put = lambda text: open(out, "w").write(text)
    put("\n".join(json.dumps(r) for r in exp) + "\n")
    check("the key itself", A.grade_t1(run, None, KEYS)[0], 1.0)
    put("\n".join(json.dumps(dict(e, qty=float(e["qty"]), refund=int(e["refund"]))) for e in exp) + "\n")
    check("exploit: qty as 8.0 and refund as 0/1", A.grade_t1(run, None, KEYS)[0], 0.0)
    put("\n".join(json.dumps(r) for r in reversed(exp)) + "\nnot json\n")
    check("exploit: reversed order plus a stray line", A.grade_t1(run, None, KEYS)[0], 0.0)
    put("header\n" + "\n".join(json.dumps(r) for r in exp) + "\n")
    check("right order plus a stray header line", A.grade_t1(run, None, KEYS)[0], 1.0)

    print("t4: the loader, and the test the spec did not entail")
    ref = open(os.path.join(HERE, "src", "solution_ok.py")).read()
    sol = os.path.join(d, "solution.py")
    open(sol, "w").write(ref)
    check("the reference", A.grade_t4(run, None, KEYS)[0], 1.0)
    open(sol, "w").write("from __future__ import annotations\nfrom dataclasses import dataclass\n"
                         "@dataclass\nclass C:\n    a: int\n    b: int\n" + ref)
    check("exploit: future annotations + @dataclass", A.grade_t4(run, None, KEYS)[0], 1.0)
    strict = ref.replace("    for start, end in intervals:\n        if start > end:",
                         "    for pair in intervals:\n        if not isinstance(pair, tuple) or len(pair) != 2:\n"
                         "            raise TypeError('pair')\n    for start, end in intervals:\n        if start > end:")
    assert strict != ref
    open(sol, "w").write(strict)
    check("exploit: a solution that rejects list pairs is also correct", A.grade_t4(run, None, KEYS)[0], 1.0)
    open(sol, "w").write("import sys\nsys.exit(3)\n")
    check("a solution that exits at import scores 0, grader survives", A.grade_t4(run, None, KEYS)[0], 0.0)

    print("contamination")
    root = os.path.join(d, "sweep")
    mine = os.path.join(root, "t2-haiku-low-1", "work")

    def tr(command, result):
        f = os.path.join(d, "t.jsonl")
        recs = [
            {"type": "assistant", "timestamp": "2026-10-09T00:00:00Z", "requestedModel": "claude-haiku-5-5",
             "effort": "low", "requestId": "r1",
             "message": {"id": "m", "usage": {"input_tokens": 1, "output_tokens": 1},
                         "content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}]}},
            {"type": "user", "timestamp": "2026-10-09T00:00:05Z",
             "message": {"content": [{"type": "tool_result", "content": result}]}},
        ]
        open(f, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
        return A.read_transcript(f, mine)

    t = tr("tail -n +3 evals/tier-sweep/keys/t2_answers.json | head -12", '"q1": 9,')
    check("exploit: tail of a key file, canary not in the output", (bool(t["saw_private"]), t["canary"]), (True, False))
    t = tr("grep -rn available .", "evals/tier-sweep/src/ledger_ok.py:49:        if qty > self.available(sku):")
    check("exploit: recursive grep from the repo, path only in the RESULT", bool(t["saw_private"]), True)
    t = tr("sed -n '19,64p' src/hidden_tests.py", "...")
    check("exploit: sed of the hidden tests by relative path", bool(t["saw_private"]), True)
    t = tr("cat %s/t1-opus-high-2/work/output.jsonl" % root, "{}")
    check("another run's output named in a command", bool(t["saw_private"]), True)
    t = tr("ls %s" % root, "t1-opus-high-2")
    check("listing the sweep root", bool(t["saw_private"]), True)
    t = tr("cd %s && grep -c CRITICAL service.log" % mine, "9")
    check("an ordinary in-directory command is clean", (t["saw_private"], t["outside_run_dir"]), ([], []))
    t = tr("ls", "README.md agents evals")
    check("a bare ls from the start directory is a warning, not a void", (bool(t["saw_private"]), len(t["outside_run_dir"])), (False, 1))

    shutil.rmtree(d)
    print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
