#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key
"""Regression tests for the graders. Run: python3 test_graders.py

Two adversarial reviews of these graders ran before the sweep did. Every case marked
"exploit" is something one of them demonstrated against an earlier version, kept because
each was a working repro and not a theory:

  review 1  a recall-only review grader paid full marks for one guess per spec clause;
            a proximity rule credited a false finding beside a seeded one; a hidden test
            demanded behaviour the spec did not state; the module loader zeroed a correct
            solution; a partial read of a key file went undetected.
  review 2  the keyword gate that replaced proximity credited "X may not be atomic" for
            every clause and missed 59 natural phrasings of real findings; restating one
            defect under three clauses scored below missing it; a run that named its own
            script analyze.py was voided.

The t3 grader no longer reads prose at all, which is what closed the second set.
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

# One minimal repro per seeded defect. Also the plainest statement of what each defect is.
REPRO = {
    "B1": 'inv = Inventory(); inv.add_stock("a", 5)\ninv.remove_stock("a", 5)\nassert inv.on_hand("a") == 0',
    "B2": 'inv = Inventory(); inv.add_stock("a", 5)\nassert inv.low_stock(5) == []',
    "B3": ('inv = Inventory(); inv.add_stock("a", 5); inv.reserve("a", 4, "o1")\n'
           'try:\n    inv.reserve("a", 2, "o2")\nexcept InsufficientStock:\n    pass\n'
           'else:\n    raise AssertionError("double-booked")'),
    "B4": 'assert Inventory().release("never-seen") == 0',
    "B5": 'assert Inventory.price_total([("a", 1)], {"a": 150}, 1) == 148',
    "B6": ('inv = Inventory(); inv.add_stock("a", 5); inv.reserve("a", 1, "o1")\n'
           'try:\n    inv.apply_batch([("reserve", ("a", 1, "o1")), ("remove_stock", ("a", 99))])\n'
           'except InsufficientStock:\n    pass\nassert inv.available("a") == 4'),
    "B7": 'inv = Inventory(); inv.add_stock("a", 5)\nassert inv.history("a", limit=0) == []',
    "B8": ('inv = Inventory(); inv.add_stock("a", 5); inv.reserve("a", 2, "o1"); inv.fulfil("o1")\n'
           'assert inv.available("a") == 3'),
    "B9": ('inv = Inventory()\ntry:\n    inv.add_stock("a", True)\nexcept ValueError:\n    pass\n'
           'else:\n    raise AssertionError("bool accepted")'),
    "B10": ('a = Inventory(); b = Inventory(); b.add_stock("x", 3); b.reserve("x", 1, "o1")\n'
            'a.merge(b)\nassert a.on_hand("x") == 3'),
    "B11": ('inv = Inventory(); inv.add_stock("a", 5)\nh = inv.history("a"); h[0]["qty"] = 999\n'
            'assert inv.history("a")[0]["qty"] == 5'),
}


def check(name, got, want, cmp="eq"):
    ok = (got == want) if cmp == "eq" else (got < want)
    print("  %s %-70s %s" % ("ok  " if ok else "FAIL", name, "" if ok else "got %r, want %s %r" % (got, cmp, want)))
    if not ok:
        FAILED.append(name)


def F(bid, **kw):
    b = [x for x in BUGS if x["id"] == bid][0]
    f = {"line": b["line"], "clause": b["clause"], "description": b["desc"], "repro": REPRO[bid]}
    f.update(kw)
    return f


def main():
    d = tempfile.mkdtemp()
    run = {"dir": d}
    g3 = lambda fs: A.grade_t3(run, {"findings": fs}, KEYS)
    ids = [b["id"] for b in BUGS]
    real = [F(i) for i in ids]
    n = len(ids)

    print("t3: every seeded defect has a repro that shows it, and only it")
    assert set(REPRO) == set(ids), "a seeded defect has no canonical repro"
    for i in ids:
        check("%s alone is credited with exactly %s" % (i, i), g3([F(i)])[1]["found"], [i])
    check("all of them together score 1.0", g3(real)[0], 1.0)

    print("t3 exploit: prose earns nothing")
    restate = [{"line": l, "clause": c, "description": t} for l, c, t in [
        (109, 9, "apply_batch may not be atomic"),
        (72, 5, "after fulfil returns, the order may still hold a reservation"),
        (38, 1, "add_stock may not raise ValueError for every qty that is not a true positive integer"),
        (87, 7, "history may not return copies, and limit=0 may not return an empty list"),
        (133, 10, "merge may not add other's on-hand quantities")]]
    check("each clause negated, no repro", g3(restate)[0], 0.0)
    check("the key's own descriptions, no repro", g3([dict(f, repro=None) for f in real])[0], 0.0)
    check("the key's own descriptions with `assert False`", g3([dict(f, repro="assert False") for f in real])[0], 0.0)
    check("the key's own descriptions with a repro that passes everywhere",
          g3([dict(f, repro="inv = Inventory()") for f in real])[0], 0.0)
    wrong = [{"line": 123, "clause": 9, "description": "except Exception does not catch KeyboardInterrupt, so not atomic",
              "repro": ('class K:\n    def __hash__(self):\n        raise KeyboardInterrupt\n'
                        'inv = Inventory()\ntry:\n    inv.apply_batch([("add_stock", ("a", 1)), ("add_stock", (K(), 1))])\n'
                        'except BaseException:\n    pass\nassert inv.on_hand("a") == 0')}]
    check("a true-but-out-of-contract finding (BaseException) is not credited as B6", g3(wrong)[1]["found"], [])

    print("t3: phrasing does not matter, the repro does")
    odd = [dict(F(i), description="see repro", clause=0, line=1) for i in ids]
    check("wrong line, wrong clause, empty description, working repros", g3(odd)[0], 1.0)
    check("a repro that imports from ledger is graded on what it shows",
          g3([F("B4", repro="from ledger import Inventory\n" + REPRO["B4"])])[1]["found"], ["B4"])
    check("a repro that prints is fine", g3([F("B2", repro='print("checking")\n' + REPRO["B2"])])[1]["found"], ["B2"])

    print("t3: duplicates, padding and breadth")
    dup = real + [F("B9", clause=2), F("B9", clause=3)]
    check("exploit: a defect restated under two more clauses is not padding", g3(dup)[0], 1.0)
    check("...and is counted as 2 duplicates", g3(dup)[1]["duplicates"], 2)
    miss = [F(i) for i in ids if i != "B9"]
    check("exploit: missing a defect now scores below restating one", g3(miss)[0], g3(dup)[0], "lt")
    pad = real + [{"line": 3, "clause": 1, "description": "speculative concern %d" % i} for i in range(8)]
    check("padding costs: R 1.0, P n/(n+8)", round(g3(pad)[0], 4), round(2 * n / (2 * n + 8), 4))
    both = {"line": 89, "clause": 7, "description": "limit and copies", "repro": REPRO["B7"] + "\n" + REPRO["B11"]}
    check("one repro that shows two defects is credited with one", len(g3([both])[1]["found"]), 1)
    check("...and a second finding then picks up the other", g3([both, F("B11")])[1]["found"], ["B7", "B11"])
    check("an expectation the spec does not support costs precision",
          g3(real + [{"line": 84, "clause": 6, "description": "threshold should be inclusive",
                      "repro": 'inv = Inventory(); inv.add_stock("a", 5)\nassert inv.low_stock(5) == ["a"]'}])[0], 1.0, "lt")
    check("no findings at all", g3([])[0], 0.0)

    print("t3: a hostile or broken repro does not take the grader down")
    check("an infinite loop times out and earns nothing", g3([F("B1", repro="while True:\n    pass")])[0], 0.0)
    check("sys.exit(0) earns nothing", g3([F("B1", repro="import sys\nsys.exit(0)")])[0], 0.0)
    check("a syntax error earns nothing", g3([F("B1", repro="assert (")])[0], 0.0)
    check("...and the findings beside it are still graded", g3([F("B1", repro="assert ("), F("B2")])[1]["found"], ["B2"])

    print("t1: types, order, and one rule for every malformation")
    exp = KEYS["t1"]
    out = os.path.join(d, "output.jsonl")
    put = lambda text: open(out, "w").write(text)
    J = lambda rows: "\n".join(json.dumps(r) for r in rows) + "\n"
    g1 = lambda: round(A.grade_t1(run, None, KEYS)[0], 4)
    put(J(exp)); check("the key itself", g1(), 1.0)
    put(J([dict(e, qty=float(e["qty"]), refund=int(e["refund"])) for e in exp]))
    check("exploit: qty as 8.0 and refund as 0/1", g1(), 0.0)
    put(J(list(reversed(exp))) + "not json\n"); check("exploit: reversed order plus a stray line", g1(), round(1 / 41, 4))
    put("header\n" + J(exp)); check("a stray header line costs one line's worth", g1(), round(40 / 41, 4))
    put(J(exp + [exp[-1]])); check("exploit: a duplicated last line costs the same", g1(), round(40 / 41, 4))
    put(J(exp[1:] + [exp[0]])); check("exploit: one record moved costs one record", g1(), round(39 / 40, 4))
    put(J([dict(exp[0], id=["x"])] + exp[1:])); check("exploit: an unhashable id does not crash the grader", g1(), round(39 / 40, 4))

    print("t4: the loader, and the test the spec did not entail")
    ref = open(os.path.join(HERE, "src", "solution_ok.py")).read()
    sol = os.path.join(d, "solution.py")
    g4 = lambda: A.grade_t4(run, None, KEYS)[0]
    open(sol, "w").write(ref); check("the reference", g4(), 1.0)
    open(sol, "w").write("from __future__ import annotations\nfrom dataclasses import dataclass\n"
                         "@dataclass\nclass C:\n    a: int\n    b: int\n" + ref)
    check("exploit: future annotations + @dataclass", g4(), 1.0)
    strict = ref.replace("    for start, end in intervals:\n        if start > end:",
                         "    for pair in intervals:\n        if not isinstance(pair, tuple) or len(pair) != 2:\n"
                         "            raise TypeError('pair')\n    for start, end in intervals:\n        if start > end:")
    assert strict != ref
    open(sol, "w").write(strict); check("exploit: a solution that rejects list pairs is also correct", g4(), 1.0)
    open(sol, "w").write("import sys\nsys.exit(3)\n"); check("a solution that exits at import scores 0", g4(), 0.0)

    print("contamination: what voids a run, and what must not")
    root = os.path.join(d, "sweep")
    me = {"dir": os.path.join(root, "t2-haiku-low-1", "work")}
    others = ["t1-opus-high-2", "t4-opus-high-1"]
    vault = "/home/someone/.cache/vault"

    def tr(command, result, tool="Bash", key="command"):
        f = os.path.join(d, "t.jsonl")
        recs = [
            {"type": "assistant", "timestamp": "2026-10-09T00:00:00Z", "requestedModel": "claude-haiku-5-5",
             "effort": "low", "requestId": "r1",
             "message": {"id": "m", "usage": {"input_tokens": 1, "output_tokens": 1},
                         "content": [{"type": "tool_use", "name": tool, "input": {key: command}}]}},
            {"type": "user", "timestamp": "2026-10-09T00:00:05Z",
             "message": {"content": [{"type": "tool_result", "content": result}]}},
        ]
        open(f, "w").write("\n".join(json.dumps(r) for r in recs) + "\n")
        t = A.read_transcript(f, me, others, vault)
        return ("void" if t["void"] else "warn" if t["warn"] else "clean")

    w = me["dir"]
    check("exploit: tail of a key file by its path", tr("tail -n +3 evals/tier-sweep/keys/t2_answers.json", '"q1": 9,'), "void")
    check("exploit: recursive grep, private path only in the RESULT",
          tr("cd %s && grep -rn available /home/x/Repos" % w, "evals/tier-sweep/src/ledger_ok.py:49: if qty >"), "void")
    check("git history shows a private path in its output", tr("cd %s && git -C /r log -p" % w, "+++ b/evals/tier-sweep/src/hidden_tests.py"), "void")
    check("the vault named in a command", tr("ls %s" % vault, "keys src"), "void")
    check("another run's output named in a command", tr("cat %s/t1-opus-high-2/work/output.jsonl" % root, "{}"), "void")
    check("listing the sweep root", tr("ls %s" % root, "x"), "void")
    check("exploit: a sibling reached by relative path, id in the command",
          tr("cd %s && cat ../../t4-opus-high-1/work/solution.py" % w, "def parse_duration"), "void")
    check("exploit: `ls ../..` whose RESULT lists the other runs", tr("cd %s && ls ../.." % w, "t1-opus-high-2\nt2-haiku-low-1"), "void")
    check("`ls ../..` on its own is a warning", tr("cd %s && ls ../.." % w, "(nothing useful)"), "warn")
    check("exploit: a script the run itself names analyze.py is innocent",
          tr("cd %s && cat > analyze.py <<'E'\nimport re\nE\npython3 analyze.py" % w, "9"), "clean")
    check("exploit: copying ledger.py to ledger_ok.py is a warning, not a void",
          tr("cd %s && cp ledger.py ledger_ok.py" % w, ""), "warn")
    check("exploit: the answer itself may say hidden_tests", tr("ran my own hidden_tests equivalent", "", tool="StructuredOutput", key="self_check"), "clean")
    check("exploit: a path that merely starts like the sweep root",
          tr("cd %s && python3 %s_check.py" % (w, root), "ok"), "clean")
    check("an ordinary in-directory command", tr("cd %s && grep -c CRITICAL service.log" % w, "9"), "clean")
    check("a bare ls from the start directory is a warning", tr("ls", "README.md agents evals"), "warn")

    shutil.rmtree(d)
    print("\n%d failed" % len(FAILED) if FAILED else "\nall passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
