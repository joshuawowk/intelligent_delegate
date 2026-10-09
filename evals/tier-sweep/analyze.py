#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key   (this file reads the keys; a run that read it is void)
"""Grade a tier-sweep run and read what each agent actually was from its transcript.

    python3 analyze.py <workflow-transcript-dir> <args.json> [--json out.json] [--vault DIR]

Nothing here trusts an agent's account of itself, and nothing here reads prose. Model
and effort come from the `requestedModel` / `effort` fields the harness wrote on each
assistant record; tokens from per-request `usage`; duration is last record minus first.
Quality comes from the graders below, each of which compares values or runs code:

    t1  JSON equality, value and type, record by record
    t2  exact match on ten answers
    t3  each finding's repro is executed against a correct ledger and against one
        single-defect variant per seeded defect
    t4  42 hidden tests

A run is VOID, and listed, when its transcript shows it had an answer in front of it —
the key canary, the path of a private file, or another run's directory — when it
consulted the advisor (a second model did some of the work), or when the model/effort
it ran at is not the arm it was assigned. Things that merely look odd are listed as
warnings and kept.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
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

# A private file reached BY PATH: the run is void. These need the directory in them. A
# bare name is not enough — "analyze.py" is what a model naturally calls a script it
# writes to study a log, and an earlier version voided exactly that innocent run.
PRIVATE_PATHS = ["tier-sweep/keys", "tier-sweep/src", "tier-sweep/build_fixtures",
                 "tier-sweep/analyze", "tier-sweep/test_graders", "intelligent_delegate/.work",
                 ".work/audit", ".work/pilot", ".work/design", ".work/sweep"]
# A private file's NAME with no path: a warning to read, never a void.
PRIVATE_NAMES = ["t1_expected", "t2_answers", "t3_bugs", "t3_variants", "hidden_tests",
                 "ledger_ok", "ledger_mutations", "ledger_tests", "solution_ok", "build_fixtures"]


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def foreign(blob, run, others, vault):
    """Why `blob` shows this run reached an answer, or None."""
    for frag in PRIVATE_PATHS:
        if frag in blob:
            return "names the private path %s" % frag
    if vault and vault in blob:
        return "names the vault"
    own = os.path.basename(os.path.dirname(run["dir"]))
    root = os.path.dirname(os.path.dirname(run["dir"]))
    # the sweep root itself, or anything under it that is not this run. The lookahead
    # keeps /tmp/sweep from matching /tmp/sweep_check.py.
    for m in re.finditer(re.escape(root) + r"(?![A-Za-z0-9_.\-])(?:/([A-Za-z0-9_.\-]+))?", blob):
        if m.group(1) != own:
            return "reaches %s" % (m.group(1) or "the sweep root")
    for rid in others:
        if rid in blob:
            return "names another run, %s" % rid
    return None


def read_transcript(path, run, others=(), vault=None):
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
    usage = {}          # requestId -> usage; the last record for a request wins
    tools = {}
    advisor_calls = 0
    void, warn = [], []
    for r in recs:
        kind = r.get("type")
        msg = r.get("message") or {}
        if kind == "user":
            content = msg.get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result":
                    blob = json.dumps(c.get("content"))
                    why = foreign(blob, run, others, vault)
                    if why:
                        void.append("a tool result " + why)
            continue
        if kind != "assistant":
            continue
        if r.get("requestedModel"):
            models.add(r["requestedModel"])
        if r.get("effort"):
            efforts.add(r["effort"])
        if r.get("advisorModel"):
            advisor_models.add(r["advisorModel"])
        rid = r.get("requestId") or msg.get("id")
        if msg.get("usage") and rid:
            usage[rid] = (msg["usage"], r.get("requestedModel") or msg.get("model"))
        for c in msg.get("content") or []:
            t = c.get("type")
            if t == "tool_use":
                name = c.get("name", "?")
                tools[name] = tools.get(name, 0) + 1
                if name == "StructuredOutput":
                    continue        # the run's own answer; it may say anything
                blob = json.dumps(c.get("input", {}))
                why = foreign(blob, run, others, vault)
                if why:
                    void.append("%s input %s" % (name, why))
                    continue
                bare = [n for n in PRIVATE_NAMES if n in blob]
                if bare:
                    warn.append("%s input mentions the name %s" % (name, bare[0]))
                elif "../.." in blob:
                    warn.append("%s input climbs above the run directory: %s" % (name, blob[:90]))
                elif run["dir"] not in blob:
                    warn.append("%s input does not name the run directory: %s" % (name, blob[:90]))
            elif t == "server_tool_use" and "advisor" in (c.get("name") or ""):
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
        cw1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
        cw5 = cc.get("ephemeral_5m_input_tokens")
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
        "advisor_calls": advisor_calls, "canary": CANARY in raw, "void": void, "warn": warn,
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
    """Records that are right AND in the input's order, over the larger of how many were
    expected and how many lines were written.

    One rule for every malformation, so a duplicated line, a stray note and a moved
    record each cost in proportion: an earlier version scored a duplicated last line 0.0
    and a trailing note 1.0.
    """
    path = os.path.join(run["dir"], "output.jsonl")
    if not os.path.exists(path):
        return 0.0, {"error": "no output.jsonl"}
    exp = keys["t1"]
    index = {e["id"]: i for i, e in enumerate(exp)}
    lines = [l.strip() for l in open(path, errors="replace") if l.strip()]
    seq = []            # expected index of each line that is a fully correct record
    for line in lines:
        try:
            g = json.loads(line)
        except Exception:
            continue
        rid = g.get("id") if isinstance(g, dict) else None
        if isinstance(rid, str) and rid in index and same(g, exp[index[rid]]):
            seq.append(index[rid])
    # longest strictly increasing subsequence: the correct records that keep their order
    tails = []
    for x in seq:
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if tails[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        if lo == len(tails):
            tails.append(x)
        else:
            tails[lo] = x
    ok = len(tails)
    return ok / max(len(exp), len(lines)), {"in_order_and_right": ok, "right": len(set(seq)),
                                            "expected": len(exp), "lines": len(lines)}


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


REPRO_RUNNER = r'''
import contextlib, importlib.util, io, json, signal, sys
spec = json.load(sys.stdin)
class _Timeout(BaseException):
    pass
def _alarm(*_):
    raise _Timeout()
signal.signal(signal.SIGALRM, _alarm)
out = {}
for name, path in spec["variants"].items():
    s = importlib.util.spec_from_file_location("ledger", path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    # The brief says not to import from ledger. A repro that does anyway is graded on
    # what it demonstrates, not on that habit: `ledger` resolves to this variant.
    sys.modules["ledger"] = m
    row = []
    for src in spec["repros"]:
        g = {"Inventory": m.Inventory, "InsufficientStock": m.InsufficientStock, "__name__": "repro"}
        try:
            signal.setitimer(signal.ITIMER_REAL, 3.0)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                exec(compile(src, "<repro>", "exec"), g)
            row.append("pass")
        except _Timeout:
            row.append("fail:Timeout")
        except BaseException as e:
            row.append("fail:" + type(e).__name__)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
    out[name] = row
sys.__stdout__.write("\n" + json.dumps(out) + "\n")
'''


def run_repros(repros, variants):
    """{variant: ['pass' | 'fail:<Exception>', ...]} — one verdict per repro."""
    with tempfile.TemporaryDirectory() as tmp:
        p = subprocess.run([sys.executable, "-I", "-c", REPRO_RUNNER],
                           input=json.dumps({"variants": variants, "repros": repros}),
                           capture_output=True, text=True, timeout=180, cwd=tmp)
    return json.loads(p.stdout.strip().split("\n")[-1])


def grade_t3(run, result, keys):
    """Each finding is judged by running its repro, and by nothing else.

    A repro DEMONSTRATES a defect when it passes on the reference ledger and fails on the
    ledger the reviewer was given. It is then credited with every seeded defect whose
    single-mutation variant it also fails on — the reference with that one defect and no
    other. So "apply_batch may not be atomic" earns nothing, and a correct finding earns
    its credit however it is phrased.

    Credit is assigned by maximum bipartite matching: one finding counts for at most one
    defect, one defect is counted at most once. A demonstrating finding left over because
    every defect it shows is already credited is a DUPLICATE — the same defect reported
    twice — and is dropped from the precision denominator rather than counted as padding.

    Score is F1. Precision is credited findings over non-duplicate findings, so a finding
    with no repro, a repro that fails on a correct ledger, or a repro that does not fail
    on the given one all cost the reviewer.
    """
    bugs = keys["t3"]
    if not isinstance(result, dict):
        return 0.0, {"error": "no structured result"}
    findings = [f for f in (result.get("findings") or []) if isinstance(f, dict)]
    n = len(findings)
    repros = [f.get("repro") if isinstance(f.get("repro"), str) else "raise RuntimeError('no repro given')"
              for f in findings]
    verdict = run_repros(repros, keys["t3_variants"]) if n else {}
    ids = [b["id"] for b in bugs]
    shows, kills = [], []
    for i in range(n):
        ok = verdict["reference"][i] == "pass" and verdict["buggy"][i] != "pass"
        shows.append(ok)
        kills.append([j for j, bid in enumerate(ids) if ok and verdict[bid][i] != "pass"])
    owner = {}

    def place(i, seen):
        for j in kills[i]:
            if j in seen:
                continue
            seen.add(j)
            if j not in owner or place(owner[j], seen):
                owner[j] = i
                return True
        return False

    for i in range(n):
        if kills[i]:
            place(i, set())
    used = set(owner.values())
    matched = [ids[j] for j in sorted(owner)]
    dup = [i for i in range(n) if i not in used and kills[i] and all(j in owner for j in kills[i])]
    recall = len(matched) / len(bugs)
    denom = n - len(dup)
    precision = (len(used) / denom) if denom else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    by_diff = {}
    for b in bugs:
        d = by_diff.setdefault(b["difficulty"], [0, 0])
        d[1] += 1
        d[0] += 1 if b["id"] in matched else 0

    def why(i):
        if not isinstance(findings[i].get("repro"), str):
            return "no repro"
        if verdict["reference"][i] != "pass":
            return "repro fails on a correct ledger (%s)" % verdict["reference"][i][5:]
        if verdict["buggy"][i] == "pass":
            return "repro does not fail on the given ledger"
        return "fails on the given ledger, passes on the reference, yet no single seeded defect explains it"

    unmatched = [{"line": findings[i].get("line"), "clause": findings[i].get("clause"), "why": why(i),
                  "description": str(findings[i].get("description", ""))[:220]}
                 for i in range(n) if i not in used and i not in dup]
    return f1, {"recall": round(recall, 4), "precision": round(precision, 4), "findings": n,
                "found": matched, "missed": [b for b in ids if b not in matched],
                "duplicates": len(dup), "unmatched": unmatched, "by_difficulty": by_diff}


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
    k = os.path.join(HERE, "keys")
    t1 = [json.loads(l) for l in open(os.path.join(k, "t1_expected.jsonl")) if l.strip() and not l.startswith("#")]
    t2 = json.load(open(os.path.join(k, "t2_answers.json")))["answers"]
    t3 = json.load(open(os.path.join(k, "t3_bugs.json")))["bugs"]
    variants = {"reference": os.path.join(k, "t3_variants", "reference.py"),
                "buggy": os.path.join(HERE, "fixtures", "t3", "ledger.py")}
    for b in t3:
        variants[b["id"]] = os.path.join(k, "t3_variants", b["id"] + ".py")
    for name, path in variants.items():
        assert os.path.exists(path), "missing t3 variant %s — run build_fixtures.py (or seal.py restore)" % name
    return {"t1": t1, "t2": t2, "t3": t3, "t3_variants": variants}


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    tdir, args_path = argv[1], argv[2]
    vault = os.path.abspath(argv[argv.index("--vault") + 1]) if "--vault" in argv else None
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
    rows, seen = [], set()
    for aid, lab in label.items():
        if lab not in runs:
            continue
        run = runs[lab]
        seen.add(lab)
        path = os.path.join(tdir, "agent-%s.jsonl" % aid)
        others = [r for r in runs if r != lab]
        tr = read_transcript(path, run, others, vault) if os.path.exists(path) else {}
        res = result.get(aid)
        try:
            score, detail = GRADERS[run["task"]](run, res, keys)
        except Exception as e:          # one malformed answer must not stop the grading of the rest
            score, detail = 0.0, {"error": "grader raised %r" % (e,)}
        why = []
        if tr.get("canary"):
            why.append("read an answer key (canary)")
        if tr.get("void"):
            why.append(tr["void"][0])
        if tr.get("advisor_calls"):
            why.append("consulted the advisor x%d" % tr["advisor_calls"])
        if tr.get("models") != [ALIAS[run["model"]]]:
            why.append("ran %s, assigned %s" % (tr.get("models"), run["model"]))
        if tr.get("efforts") != [run["effort"]]:
            why.append("ran effort %s, assigned %s" % (tr.get("efforts"), run["effort"]))
        rows.append(dict(run, agentId=aid, returned=res is not None, score=round(score, 4), detail=detail,
                         excluded=why, **tr))
    missing = sorted(set(runs) - seen)
    if "--json" in argv:
        json.dump({"rows": rows, "never_started": missing}, open(argv[argv.index("--json") + 1], "w"), indent=1)

    # ---------------------------------------------------------------- report
    print("runs: %d graded, %d never started, %d void" % (len(rows), len(missing), sum(1 for r in rows if r["excluded"])))
    for r in rows:
        if r["excluded"]:
            print("  VOID %-22s %s" % (r["id"], "; ".join(r["excluded"])))
    for r in rows:
        if not r["returned"]:
            print("  NO RETURN %-22s" % r["id"])
    for r in rows:
        if "error" in r["detail"]:
            print("  GRADER  %-22s %s" % (r["id"], r["detail"]["error"]))
    warned = [r for r in rows if r.get("warn") and not r["excluded"]]
    if warned:
        print("  %d run(s) kept with a warning to read:" % len(warned))
        for r in warned:
            print("    %-22s x%d  e.g. %s" % (r["id"], len(r["warn"]), r["warn"][0][:130]))
    good = [r for r in rows if not r["excluded"]]

    def agg(sel):
        if not sel:
            return None
        n = len(sel)
        mean = lambda k: sum(r[k] for r in sel) / n
        secs = sorted(r["seconds"] for r in sel)
        return {"n": n, "score": mean("score"), "min": min(r["score"] for r in sel), "sec": mean("seconds"),
                "med": secs[n // 2] if n % 2 else (secs[n // 2 - 1] + secs[n // 2]) / 2,
                "cost": mean("cost_usd"), "out": sum(r["tokens"]["out"] for r in sel) / n,
                "think": sum(r["tokens"]["think"] for r in sel) / n,
                "req": mean("requests"), "maxreq": max(r["requests"] for r in sel),
                "prompt": max(r["max_prompt_tokens"] for r in sel)}

    arms = []
    for r in good:
        a = (r["model"], r["effort"])
        if a not in arms:
            arms.append(a)
    order = {"haiku": 0, "sonnet": 1, "opus": 2}
    eo = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
    arms.sort(key=lambda a: (order[a[0]], eo[a[1]]))
    tasks = [t for t in ("t1", "t2", "t3", "t4") if any(r["task"] == t for r in good)]
    for task in tasks:
        sel_t = [r for r in good if r["task"] == task]
        print("\n%s  (%s)" % (task, sel_t[0]["agentType"]))
        print("  %-14s %2s %6s %6s %7s %7s %8s %8s %7s %5s %6s %9s" % (
            "arm", "n", "score", "min", "sec", "median", "cost $", "out tok", "think", "reqs", "maxreq", "max prompt"))
        for a in arms:
            g = agg([r for r in sel_t if (r["model"], r["effort"]) == a])
            if g:
                print("  %-14s %2d %6.3f %6.3f %7.1f %7.1f %8.4f %8.0f %7.0f %5.1f %6d %9d" % (
                    "%s/%s" % a, g["n"], g["score"], g["min"], g["sec"], g["med"], g["cost"], g["out"],
                    g["think"], g["req"], g["maxreq"], g["prompt"]))
    t3rows = [r for r in good if r["task"] == "t3" and "recall" in r["detail"]]
    if t3rows:
        print("\nt3 detail — the score above is F1; these are its parts")
        print("  %-14s %2s %7s %9s %9s %5s %10s   %s" % ("arm", "n", "recall", "precision", "findings", "dups", "unmatched", "found, by difficulty"))
        for a in arms:
            sel = [r for r in t3rows if (r["model"], r["effort"]) == a]
            if not sel:
                continue
            n = len(sel)
            d = {}
            for r in sel:
                for k, (hit, of) in r["detail"]["by_difficulty"].items():
                    d.setdefault(k, [0, 0]); d[k][0] += hit; d[k][1] += of
            print("  %-14s %2d %7.3f %9.3f %9.1f %5.1f %10.1f   %s" % (
                "%s/%s" % a, n, sum(r["detail"]["recall"] for r in sel) / n,
                sum(r["detail"]["precision"] for r in sel) / n,
                sum(r["detail"]["findings"] for r in sel) / n,
                sum(r["detail"]["duplicates"] for r in sel) / n,
                sum(len(r["detail"]["unmatched"]) for r in sel) / n,
                "  ".join("%s %d/%d" % (k, d[k][0], d[k][1]) for k in ("easy", "medium", "hard") if k in d)))
        um = [(r["id"], x) for r in t3rows for x in r["detail"]["unmatched"]]
        print("\n  t3 audit: %d finding(s) earned no credit. Read these — a real defect of the fixture hides here." % len(um))
        tally = {}
        for _rid, x in um:
            key = x["why"].split(" (")[0]
            tally[key] = tally.get(key, 0) + 1
        for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
            print("    %3d  %s" % (v, k))
        for rid, x in um:
            print("    %-20s L%s c%s [%s] %s" % (rid, x["line"], x["clause"], x["why"][:44], x["description"][:120]))
    if len(tasks) == 4:
        print("\nall tasks, mean of per-task means")
        print("  %-14s %6s %7s %8s" % ("arm", "score", "sec", "cost $"))
        for a in arms:
            per = [agg([r for r in good if r["task"] == t and (r["model"], r["effort"]) == a]) for t in tasks]
            if all(per):
                print("  %-14s %6.3f %7.1f %8.4f" % ("%s/%s" % a, sum(p["score"] for p in per) / 4,
                                                 sum(p["sec"] for p in per) / 4, sum(p["cost"] for p in per) / 4))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
