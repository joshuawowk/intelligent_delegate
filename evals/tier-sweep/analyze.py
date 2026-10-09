#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key   (this file reads the keys; a run that read it is contaminated)
"""Grade a tier-sweep run and read what each agent actually was from its transcript.

    python3 analyze.py <workflow-transcript-dir> <args.json> [--json out.json]

Nothing here trusts an agent's account of itself. Model and effort come from the
`requestedModel` / `effort` fields the harness wrote on each assistant record; tokens
come from per-request `usage`; duration is last record minus first; quality comes from
the deterministic graders below, run against files and structured returns.

A run is EXCLUDED, and listed, when its transcript shows it saw an answer key — the key
canary, or the path of any private file in a tool call or a tool result — when it
consulted the advisor (a second model did some of the work), or when the model/effort it
ran at is not the arm it was assigned. Tool calls that reach outside the run directory
without touching a private file are listed as warnings, not exclusions.
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CANARY = "CANARY-" + "7f3e9a1c-tier-sweep-key"

# USD per million tokens, from evals/facts-2026-10-09.md (Claude Code 2.1.295 catalog).
PRICE = {
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cw5": 0.125, "cw1h": 0.20, "cr": 0.01,
                         "long_above": 100000,
                         "long": {"in": 0.50, "out": 2.50, "cw5": 0.625, "cw1h": 1.00, "cr": 0.05}},
    "claude-sonnet-5-5": {"in": 2.0, "out": 10.0, "cw5": 2.5, "cw1h": 4.0, "cr": 0.20},
    "claude-opus-5-5": {"in": 4.0, "out": 20.0, "cw5": 5.0, "cw1h": 8.0, "cr": 0.20},
}
ALIAS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}

# Any of these in a tool input or a tool result means the run had an answer key, a
# reference implementation or the generator in front of it. The canary alone is not
# enough: it sits on the first line of each private file, so `tail`, `sed -n` or a
# recursive grep returns the contents without it — but never without the path.
PRIVATE = ("tier-sweep/keys", "tier-sweep/src", "t1_expected", "t2_answers", "t3_bugs",
           "hidden_tests", "ledger_ok", "ledger_mutations", "ledger_tests", "solution_ok",
           "build_fixtures", "analyze.py", "test_graders", ".work/")


def sibling(blob, run_dir):
    """Another run's directory named in `blob`, or None. Runs are laid out as
    <root>/<run_id>/work, so anything under <root> that is not this run's own id is a
    different arm's working files — which may already hold a finished answer."""
    own = os.path.basename(os.path.dirname(run_dir))
    root = os.path.dirname(os.path.dirname(run_dir))
    if not own or root in ("", "/"):
        return None
    for m in re.finditer(re.escape(root) + r"(?:/([A-Za-z0-9_.\-]+))?", blob):
        if m.group(1) != own:
            return m.group(1) or "<the sweep root>"
    return None


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def read_transcript(path, run_dir):
    raw = open(path, errors="replace").read()
    recs = []
    for line in raw.split("\n"):
        line = line.strip()
        if line:
            try:
                recs.append(json.loads(line))
            except Exception:
                pass
    stamps = [ts(r["timestamp"]) for r in recs if r.get("timestamp")]
    models, efforts, advisor_models = set(), set(), set()
    usage = {}          # requestId -> usage (last record for that request wins)
    tools = {}
    advisor_calls = 0
    outside = []        # reached outside the run directory, but not at a private file
    private = []        # saw a private file: the run is void
    for r in recs:
        if r.get("type") != "assistant":
            continue
        if r.get("requestedModel"):
            models.add(r["requestedModel"])
        if r.get("effort"):
            efforts.add(r["effort"])
        if r.get("advisorModel"):
            advisor_models.add(r["advisorModel"])
        msg = r.get("message") or {}
        rid = r.get("requestId") or msg.get("id")
        if msg.get("usage") and rid:
            usage[rid] = (msg["usage"], r.get("requestedModel") or msg.get("model"))
        for c in msg.get("content") or []:
            t = c.get("type")
            if t == "tool_use":
                name = c.get("name", "?")
                tools[name] = tools.get(name, 0) + 1
                blob = json.dumps(c.get("input", {}))
                hit = [f for f in PRIVATE if f in blob]
                sib = sibling(blob, run_dir)
                if hit:
                    private.append("%s input names %s" % (name, hit[0]))
                elif sib is not None and name != "StructuredOutput":
                    private.append("%s input reaches another run: %s" % (name, sib))
                elif name != "StructuredOutput" and run_dir not in blob:
                    outside.append("%s: %s" % (name, blob[:110]))
            elif t == "server_tool_use":
                if "advisor" in (c.get("name") or ""):
                    advisor_calls += 1
            elif t and "advisor" in t:
                advisor_calls += 1
    for r in recs:
        if r.get("type") != "user":
            continue
        content = (r.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for c in content:
            if c.get("type") == "tool_result":
                blob = json.dumps(c.get("content"))
                hit = [f for f in PRIVATE if f in blob]
                sib = sibling(blob, run_dir)
                if hit:
                    private.append("a tool result contains %s" % hit[0])
                elif sib is not None:
                    private.append("a tool result shows another run: %s" % sib)
    tok = {"in": 0, "out": 0, "cw": 0, "cr": 0, "think": 0}
    cost = 0.0
    max_prompt = 0
    for u, model in usage.values():
        i = u.get("input_tokens", 0) or 0
        o = u.get("output_tokens", 0) or 0
        cr = u.get("cache_read_input_tokens", 0) or 0
        cc = u.get("cache_creation") or {}
        cw5 = cc.get("ephemeral_5m_input_tokens")
        cw1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
        if cw5 is None:
            cw5 = (u.get("cache_creation_input_tokens", 0) or 0) - cw1
        tok["in"] += i; tok["out"] += o; tok["cr"] += cr; tok["cw"] += cw5 + cw1
        tok["think"] += ((u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0)
        prompt = i + cr + cw5 + cw1
        max_prompt = max(max_prompt, prompt)
        p = PRICE.get(model)
        if p:
            if p.get("long_above") and prompt > p["long_above"]:
                p = p["long"]
            cost += (i * p["in"] + o * p["out"] + cw5 * p["cw5"] + cw1 * p["cw1h"] + cr * p["cr"]) / 1e6
    return {
        "models": sorted(models), "efforts": sorted(efforts), "advisor_model": sorted(advisor_models),
        "requests": len(usage), "tool_calls": sum(tools.values()), "tools": tools,
        "seconds": (max(stamps) - min(stamps)).total_seconds() if stamps else None,
        "tokens": tok, "max_prompt_tokens": max_prompt, "cost_usd": round(cost, 5),
        "advisor_calls": advisor_calls, "canary": CANARY in raw, "saw_private": private,
        "outside_run_dir": outside,
    }


# ------------------------------------------------------------------ graders
def norm(s):
    return str(s).strip().strip('"').strip("'").strip()


def same(got, want):
    """Equal in value AND type, field by field. `8.0 == 8` and `1 == True` in Python, and
    the brief promises the grader compares types."""
    if not isinstance(got, dict) or set(got) != set(want):
        return False
    return all(type(got[k]) is type(want[k]) and got[k] == want[k] for k in want)


def grade_t1(run, result, keys):
    path = os.path.join(run["dir"], "output.jsonl")
    if not os.path.exists(path):
        return 0.0, {"error": "no output.jsonl"}
    got = []
    for line in open(path, errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            got.append(json.loads(line))
        except Exception:
            got.append(None)
    exp = keys["t1"]
    note = None
    if len(got) == len(exp):
        ok = sum(1 for g, e in zip(got, exp) if same(g, e))
    else:
        # Wrong line count. Credit a record only if it is right AND the records that are
        # present keep the input order, which the brief requires.
        index = {e["id"]: i for i, e in enumerate(exp)}
        seq = [index[g["id"]] for g in got if isinstance(g, dict) and g.get("id") in index]
        in_order = all(a < b for a, b in zip(seq, seq[1:]))
        by_id = {g.get("id"): g for g in got if isinstance(g, dict)}
        ok = sum(1 for e in exp if same(by_id.get(e["id"]), e)) if in_order else 0
        note = "line count %d != %d; order %s" % (len(got), len(exp), "kept" if in_order else "BROKEN")
    return ok / len(exp), {"correct": ok, "of": len(exp), "lines": len(got), "note": note}


def grade_t2(run, result, keys):
    ans = keys["t2"]
    if not isinstance(result, dict):
        return 0.0, {"error": "no structured result"}
    wrong = []
    for q, want in ans.items():
        got = result.get(q)
        if isinstance(want, int):
            try:
                good = int(norm(got)) == want
            except Exception:
                good = False
        elif q in ("q2", "q7"):
            good = norm(got).lower() == want.lower()
        else:
            good = norm(got) == want
        if not good:
            wrong.append(q)
    return (len(ans) - len(wrong)) / len(ans), {"wrong": wrong}


def grade_t3(run, result, keys):
    """A finding is credited as a seeded defect only when all three hold:

      - it cites a SPEC clause that defect violates,
      - its line is inside a function the defect can be reported against, and
      - its description mentions what is actually wrong (the defect's keyword list).

    The same rule for every defect: an earlier version also credited any finding within
    two lines of the fault regardless of clause, which forgave a wrong clause in short
    functions and punished it in long ones.

    Two defects can share a function, and one finding can satisfy the rule for more than
    one defect, so credit is assigned by maximum bipartite matching: each finding counts
    for at most one defect and each defect is counted at most once.

    The score is F1, not recall. The brief tells the reviewer a padded report is worse
    than a short one; a recall-only grader paid full marks for one guess per clause.
    """
    bugs, spans = keys["t3"], keys["t3_spans"]
    if not isinstance(result, dict):
        return 0.0, {"error": "no structured result"}
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]

    def span_of(line):
        for name, a, b in spans:
            if a <= line <= b:
                return name
        return None

    def num(v):
        try:
            return int(v)
        except Exception:
            return None

    cand = {i: [] for i in range(len(findings))}     # finding -> defects it may be
    near_misses = []
    for i, f in enumerate(findings):
        fl, fc = num(f.get("line")), num(f.get("clause"))
        if fl is None:
            continue
        fn = span_of(fl)
        text = str(f.get("description", "")).lower()
        located = []
        for j, b in enumerate(bugs):
            if fc in b["clauses"] and fn in b["functions"]:
                located.append(b["id"])
                if any(k in text for k in b["keywords"]):
                    cand[i].append(j)
        if located and not cand[i]:
            near_misses.append({"could_be": located, "line": fl, "clause": fc,
                                "description": str(f.get("description", ""))[:240]})
    owner = {}                                        # defect -> finding

    def place(i, seen):
        # nearest-line defects first, so a finding lands on the defect it sits beside
        fl = num(findings[i].get("line"))
        for j in sorted(cand[i], key=lambda j: abs(fl - bugs[j]["line"])):
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or place(owner[j], seen):
                owner[j] = i
                return True
        return False

    for i in range(len(findings)):
        if cand[i]:
            place(i, set())
    matched = {bugs[j]["id"] for j in owner}
    used = set(owner.values())
    n = len(findings)
    recall = len(matched) / len(bugs)
    precision = (len(used) / n) if n else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    by_diff = {}
    for b in bugs:
        k = b["difficulty"]
        by_diff.setdefault(k, [0, 0])
        by_diff[k][1] += 1
        by_diff[k][0] += 1 if b["id"] in matched else 0
    unmatched = [{"line": num(f.get("line")), "clause": num(f.get("clause")),
                  "description": str(f.get("description", ""))[:240]}
                 for i, f in enumerate(findings) if i not in used]
    return f1, {"recall": round(recall, 4), "precision": round(precision, 4), "findings": n,
                "found": sorted(matched, key=lambda x: int(x[1:])),
                "missed": [b["id"] for b in bugs if b["id"] not in matched],
                "unmatched": unmatched, "keyword_near_misses": near_misses, "by_difficulty": by_diff}


def grade_t4(run, result, keys):
    sol = os.path.join(run["dir"], "solution.py")
    if not os.path.exists(sol):
        return 0.0, {"error": "no solution.py"}
    # A real, registered module: `exec` into a bare ModuleType leaves sys.modules without
    # it, and a correct solution using @dataclass under `from __future__ import annotations`
    # then fails at import, because dataclasses looks the module up there.
    runner = (
        "import sys,json,importlib.util\n"
        "def load(n,p):\n"
        "    spec=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(spec)\n"
        "    sys.modules[n]=m; spec.loader.exec_module(m); return m\n"
        "ht=load('hidden_tests',sys.argv[1])\n"
        "try:\n"
        "    s=load('solution',sys.argv[2])\n"
        "except BaseException as e:\n"
        "    print(json.dumps({'import_error':repr(e)})); sys.exit(0)\n"
        "print(json.dumps({'results':ht.score(s)}))\n"
    )
    try:
        p = subprocess.run([sys.executable, "-I", "-c", runner, os.path.join(HERE, "src", "hidden_tests.py"), sol],
                           capture_output=True, text=True, timeout=30, cwd=run["dir"])
        data = json.loads(p.stdout.strip().split("\n")[-1])
    except Exception as e:
        return 0.0, {"error": "grader could not run solution: %r" % (e,)}
    if "import_error" in data:
        return 0.0, {"error": data["import_error"]}
    res = data["results"]
    failed = [n for n, _c, ok in res if not ok]
    return (len(res) - len(failed)) / len(res), {"failed": failed, "of": len(res)}


GRADERS = {"t1": grade_t1, "t2": grade_t2, "t3": grade_t3, "t4": grade_t4}


def load_keys():
    t1 = [json.loads(l) for l in open(os.path.join(HERE, "keys", "t1_expected.jsonl")) if l.strip() and not l.startswith("#")]
    t2 = json.load(open(os.path.join(HERE, "keys", "t2_answers.json")))["answers"]
    t3 = json.load(open(os.path.join(HERE, "keys", "t3_bugs.json")))["bugs"]
    src = open(os.path.join(HERE, "fixtures", "t3", "ledger.py")).read().split("\n")
    defs = []
    for i, l in enumerate(src):
        if l.strip().startswith("def "):
            start = i
            # walk up over the decorators, comments and blank lines that introduce it
            while start > 0 and (src[start - 1].strip().startswith(("@", "#")) or not src[start - 1].strip()):
                start -= 1
            while not src[start].strip():
                start += 1
            defs.append((start + 1, l.strip().split("(")[0].replace("def ", "")))
    spans = []
    for k, (ln, name) in enumerate(defs):
        end = defs[k + 1][0] - 1 if k + 1 < len(defs) else len(src)
        spans.append((name, ln, end))
    names = set(n for n, _a, _b in spans)
    for b in t3:
        own = [n for n, a, c in spans if a <= b["line"] <= c]
        assert own, "seeded defect %s is on a line outside every function" % b["id"]
        assert set(b.get("also_functions", [])) <= names, "%s names a function that is not in ledger.py" % b["id"]
        b["functions"] = sorted(set(own + b.get("also_functions", [])))
    return {"t1": t1, "t2": t2, "t3": t3, "t3_spans": spans}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    tdir, args_path = argv[1], argv[2]
    args = json.load(open(args_path))
    runs = {r["id"]: r for r in args["runs"]}
    keys = load_keys()
    label, result = {}, {}
    for line in open(os.path.join(tdir, "journal.jsonl")):
        o = json.loads(line)
        if o.get("type") == "started":
            label[o["agentId"]] = o.get("label")
        elif o.get("type") == "result":
            result[o["agentId"]] = o.get("result")
    rows = []
    seen = set()
    for aid, lab in label.items():
        if lab not in runs:
            continue
        run = runs[lab]
        seen.add(lab)
        path = os.path.join(tdir, "agent-%s.jsonl" % aid)
        tr = read_transcript(path, run["dir"]) if os.path.exists(path) else {}
        res = result.get(aid)
        score, detail = GRADERS[run["task"]](run, res, keys)
        why = []
        if tr.get("canary"):
            why.append("read an answer key (canary)")
        if tr.get("saw_private"):
            why.append("saw a private file: " + tr["saw_private"][0])
        if tr.get("advisor_calls"):
            why.append("consulted the advisor x%d" % tr["advisor_calls"])
        if tr.get("models") != [ALIAS[run["model"]]]:
            why.append("ran %s, assigned %s" % (tr.get("models"), run["model"]))
        if tr.get("efforts") != [run["effort"]]:
            why.append("ran effort %s, assigned %s" % (tr.get("efforts"), run["effort"]))
        rows.append(dict(run, agentId=aid, returned=res is not None, score=round(score, 4), detail=detail,
                         excluded=why, **tr))
    missing = sorted(set(runs) - seen)
    out = {"rows": rows, "never_started": missing}
    if "--json" in argv:
        json.dump(out, open(argv[argv.index("--json") + 1], "w"), indent=1)
    # ---- report
    print("runs: %d graded, %d never started, %d excluded" % (len(rows), len(missing), sum(1 for r in rows if r["excluded"])))
    for r in rows:
        if r["excluded"]:
            print("  EXCLUDED %-22s %s" % (r["id"], "; ".join(r["excluded"])))
    for r in rows:
        if not r["returned"]:
            print("  NO RETURN %-22s (score counted as graded from files where possible)" % r["id"])
    warned = [r for r in rows if r.get("outside_run_dir") and not r["excluded"]]
    if warned:
        print("  %d run(s) made a tool call that did not name their run directory (kept; inspect):" % len(warned))
        for r in warned:
            print("    %-22s x%d  e.g. %s" % (r["id"], len(r["outside_run_dir"]), r["outside_run_dir"][0][:120]))
    good = [r for r in rows if not r["excluded"]]

    def agg(sel):
        if not sel:
            return None
        n = len(sel)
        mean = lambda k: sum(r[k] for r in sel) / n
        return {"n": n, "score": mean("score"), "min": min(r["score"] for r in sel), "sec": mean("seconds"),
                "cost": mean("cost_usd"), "out": sum(r["tokens"]["out"] for r in sel) / n,
                "req": mean("requests"), "tools": mean("tool_calls"),
                "prompt": max(r["max_prompt_tokens"] for r in sel)}

    arms = []
    for r in good:
        a = (r["model"], r["effort"])
        if a not in arms:
            arms.append(a)
    order = {"haiku": 0, "sonnet": 1, "opus": 2}
    eo = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
    arms.sort(key=lambda a: (order[a[0]], eo[a[1]]))
    for task in ("t1", "t2", "t3", "t4"):
        sel_t = [r for r in good if r["task"] == task]
        if not sel_t:
            continue
        print("\n%s  (%s)" % (task, sel_t[0]["agentType"]))
        print("  %-14s %2s %7s %6s %8s %9s %8s %5s %6s %9s" % ("arm", "n", "score", "min", "seconds", "cost $", "out tok", "reqs", "tools", "max prompt"))
        for a in arms:
            g = agg([r for r in sel_t if (r["model"], r["effort"]) == a])
            if g:
                print("  %-14s %2d %7.3f %6.3f %8.1f %9.4f %8.0f %5.1f %6.1f %9d" % (
                    "%s/%s" % a, g["n"], g["score"], g["min"], g["sec"], g["cost"], g["out"], g["req"], g["tools"], g["prompt"]))
    t3rows = [r for r in good if r["task"] == "t3" and "recall" in r["detail"]]
    if t3rows:
        print("\nt3 detail — the score above is F1; these are its parts")
        print("  %-14s %2s %7s %9s %9s %10s   %s" % ("arm", "n", "recall", "precision", "findings", "unmatched", "recall easy/medium/hard"))
        for a in arms:
            sel = [r for r in t3rows if (r["model"], r["effort"]) == a]
            if not sel:
                continue
            n = len(sel)
            d = {}
            for r in sel:
                for k, (hit, of) in r["detail"]["by_difficulty"].items():
                    d.setdefault(k, [0, 0]); d[k][0] += hit; d[k][1] += of
            print("  %-14s %2d %7.3f %9.3f %9.1f %10.1f   %s" % (
                "%s/%s" % a, n, sum(r["detail"]["recall"] for r in sel) / n,
                sum(r["detail"]["precision"] for r in sel) / n,
                sum(r["detail"]["findings"] for r in sel) / n,
                sum(len(r["detail"]["unmatched"]) for r in sel) / n,
                "  ".join("%s %d/%d" % (k, d[k][0], d[k][1]) for k in ("easy", "medium", "hard") if k in d)))
        nm = [(r["id"], x) for r in t3rows for x in r["detail"]["keyword_near_misses"]]
        print("\n  keyword audit: %d finding(s) named the right clause and function but matched no keyword" % len(nm))
        for rid, x in nm:
            print("    %-20s %s L%s c%s: %s" % (rid, "/".join(x["could_be"]), x["line"], x["clause"], x["description"][:170]))
    print("\nall tasks, mean of per-task means")
    print("  %-14s %7s %8s %9s" % ("arm", "score", "seconds", "cost $"))
    for a in arms:
        per = [agg([r for r in good if r["task"] == t and (r["model"], r["effort"]) == a]) for t in ("t1", "t2", "t3", "t4")]
        per = [p for p in per if p]
        if len(per) == 4:
            print("  %-14s %7.3f %8.1f %9.4f" % ("%s/%s" % a, sum(p["score"] for p in per) / 4,
                                               sum(p["sec"] for p in per) / 4, sum(p["cost"] for p in per) / 4))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
