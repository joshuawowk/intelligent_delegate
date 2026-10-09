#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key   (this file reads the keys; a run that read it is contaminated)
"""Grade a tier-sweep run and read what each agent actually was from its transcript.

    python3 analyze.py <workflow-transcript-dir> <args.json> [--json out.json]

Nothing here trusts an agent's account of itself. Model and effort come from the
`requestedModel` / `effort` fields the harness wrote on each assistant record; tokens
come from per-request `usage`; duration is last record minus first; quality comes from
the deterministic graders below, run against files and structured returns.

A run is EXCLUDED, and listed, when its transcript contains the key canary (it read an
answer key), when it consulted the advisor (a second model did some of the work), or
when the model/effort it ran at is not the arm it was assigned.
"""
import glob
import json
import os
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
    outside = []
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
                if "intelligent_delegate" in blob:
                    outside.append(name)
            elif t == "server_tool_use":
                if "advisor" in (c.get("name") or ""):
                    advisor_calls += 1
            elif t and "advisor" in t:
                advisor_calls += 1
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
        "advisor_calls": advisor_calls, "canary": CANARY in raw, "touched_repo": outside,
    }


# ------------------------------------------------------------------ graders
def norm(s):
    return str(s).strip().strip('"').strip("'").strip()


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
    if len(got) == len(exp):
        ok = sum(1 for g, e in zip(got, exp) if g == e)
    else:
        by_id = {g.get("id"): g for g in got if isinstance(g, dict)}
        ok = sum(1 for e in exp if by_id.get(e["id"]) == e)
    return ok / len(exp), {"correct": ok, "of": len(exp), "lines": len(got)}


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
    bugs, spans = keys["t3"], keys["t3_spans"]
    if not isinstance(result, dict):
        return 0.0, {"error": "no structured result"}
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]

    def span_of(line):
        for name, a, b in spans:
            if a <= line <= b:
                return name
        return None

    matched, used = {}, set()
    for b in bugs:
        bspan = span_of(b["line"])
        best = None
        for i, f in enumerate(findings):
            if i in used:
                continue
            try:
                fl = int(f.get("line"))
            except Exception:
                continue
            try:
                fc = int(f.get("clause"))
            except Exception:
                fc = None
            near = abs(fl - b["line"]) <= 2
            same_fn = span_of(fl) == bspan and fc == b["clause"]
            if near or same_fn:
                d = abs(fl - b["line"])
                if best is None or d < best[0]:
                    best = (d, i)
        if best:
            used.add(best[1])
            matched[b["id"]] = True
    found = sorted(matched)
    by_diff = {}
    for b in bugs:
        k = b["difficulty"]
        by_diff.setdefault(k, [0, 0])
        by_diff[k][1] += 1
        by_diff[k][0] += 1 if b["id"] in matched else 0
    return len(found) / len(bugs), {"found": found, "missed": [b["id"] for b in bugs if b["id"] not in matched],
                                    "unmatched_findings": len(findings) - len(used), "by_difficulty": by_diff}


def grade_t4(run, result, keys):
    sol = os.path.join(run["dir"], "solution.py")
    if not os.path.exists(sol):
        return 0.0, {"error": "no solution.py"}
    runner = (
        "import sys,types,json\n"
        "def load(n,p):\n"
        "    m=types.ModuleType(n); exec(compile(open(p).read(),n,'exec'),m.__dict__); return m\n"
        "ht=load('hidden_tests',sys.argv[1])\n"
        "try:\n"
        "    s=load('solution',sys.argv[2])\n"
        "except Exception as e:\n"
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
    defs = [(i + 1, l.strip().split("(")[0].replace("def ", "")) for i, l in enumerate(src) if l.strip().startswith("def ")]
    spans = []
    for k, (ln, name) in enumerate(defs):
        end = defs[k + 1][0] - 1 if k + 1 < len(defs) else len(src)
        spans.append((name, ln, end))
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
            why.append("read an answer key")
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
