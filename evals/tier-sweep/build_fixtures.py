#!/usr/bin/env python3
# CANARY-7f3e9a1c-tier-sweep-key
"""Build the four tier-sweep task fixtures and their answer keys, deterministically.

    python3 build_fixtures.py            # writes fixtures/ (what agents see) and keys/

Every answer is computed from the generated artefact, never asserted from intent, and
every structural assumption a question relies on ("exactly one", "a clear winner") is
checked here and fails the build if it does not hold.

Nothing under fixtures/ may contain the canary token on the first line of this file;
keys/ and src/ all do. A transcript that contains it saw an answer key.
"""
import json
import os
import random
import shutil
import sys
import types
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
FIX = os.path.join(HERE, "fixtures")
KEYS = os.path.join(HERE, "keys")
CANARY = "CANARY-7f3e9a1c-tier-sweep-key"
SEED = 20261009


def load(name, path=None, src=None):
    m = types.ModuleType(name)
    if src is None:
        with open(path) as fh:
            src = fh.read()
    exec(compile(src, name, "exec"), m.__dict__)
    return m


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- T1
T1_BRIEF = """\
Convert every line of input.txt into one line of output.jsonl in this directory — same
order, one JSON object per line.

Input line:   id|full name|qty|unit price|date|status
              (pipe-separated; trim the spaces around each field)
Output keys:  id, first, middle, last, qty, unit_price, total, date, status, refund

Rules
- first = the first word of the name; last = the last word; middle = the words between
  them, joined by one space, with a trailing "." removed from each word; null when there
  are none.
- qty = an integer (a JSON number). It may be negative or zero.
- unit_price = a string with exactly two decimals ("5" -> "5.00", "5.5" -> "5.50").
- total = qty x unit price, as a string with exactly two decimals; negative when qty is
  negative ("-39.98"); "0.00" when qty is zero.
- date = MM/DD/YYYY rewritten as YYYY-MM-DD.
- status = by code, case-insensitive: S shipped, P pending, C cancelled, R returned,
  H on_hold; any other code -> "unknown".
- refund = true when qty < 0, otherwise false.

Worked examples
ORD-90001|Dana R. Whitfield|3|19.99|03/07/2026|S
-> {"id":"ORD-90001","first":"Dana","middle":"R","last":"Whitfield","qty":3,"unit_price":"19.99","total":"59.97","date":"2026-03-07","status":"shipped","refund":false}
ORD-90002| Li Wei |-2|5.5|12/01/2025|c
-> {"id":"ORD-90002","first":"Li","middle":null,"last":"Wei","qty":-2,"unit_price":"5.50","total":"-11.00","date":"2025-12-01","status":"cancelled","refund":true}
ORD-90003|Mary Ann K. Lopez-Diaz|1|40|01/15/2026|X
-> {"id":"ORD-90003","first":"Mary","middle":"Ann K","last":"Lopez-Diaz","qty":1,"unit_price":"40.00","total":"40.00","date":"2026-01-15","status":"unknown","refund":false}

The grader parses each output line as JSON and compares values and types with the
expected object. Do the conversion by hand or with a script, as you prefer; only
output.jsonl is graded.
"""

STATUS = {"S": "shipped", "P": "pending", "C": "cancelled", "R": "returned", "H": "on_hold"}


def t1_expected(line):
    f = [x.strip() for x in line.split("|")]
    oid, name, qty, price, date, code = f
    words = name.split()
    mid = [w[:-1] if w.endswith(".") else w for w in words[1:-1]]
    q = int(qty)
    p = Decimal(price)
    mm, dd, yy = date.split("/")
    return {
        "id": oid,
        "first": words[0],
        "middle": " ".join(mid) if mid else None,
        "last": words[-1],
        "qty": q,
        "unit_price": "%.2f" % p,
        "total": "%.2f" % (p * q) if q else "0.00",
        "date": "%s-%s-%s" % (yy, mm, dd),
        "status": STATUS.get(code.upper(), "unknown"),
        "refund": q < 0,
    }


def build_t1(rng):
    first = ["Avery", "Bao", "Chidi", "Dmitri", "Elena", "Farah", "Goran", "Hana", "Imani",
             "Jonas", "Keiko", "Luca", "Mirela", "Nadia", "Omar", "Priya", "Quentin", "Rosa",
             "Soren", "Tamsin", "Ulises", "Vera", "Wendell", "Xiomara", "Yusuf", "Zofia"]
    last = ["Abara", "Brandt", "Castellanos", "Dvorak", "Eriksen", "Faulkner", "Greaves",
            "Haddad", "Ivanova", "Jaramillo", "Kowalczyk", "Lindqvist", "Marchetti", "Nakamura",
            "Okonkwo", "Petrov", "Quigley", "Rasmussen", "Sandoval", "Thackeray"]
    middles = {2: "R.", 7: "Ann", 11: "J. P.", 19: "T.", 23: "Lee Q.", 31: "M.", 36: "de"}
    negative = {5, 14, 27, 33}
    zero = {17}
    lower = {3: "s", 9: "p", 18: "r", 26: "h", 35: "c"}
    unknown = {12: "X", 29: "q"}
    spaced = {1, 8, 16, 22, 30, 38}
    hyphen = {6, 21}
    lines = []
    for i in range(40):
        name = [rng.choice(first)]
        if i in middles:
            name.append(middles[i])
        ln = rng.choice(last)
        if i in hyphen:
            ln = ln + "-" + rng.choice([x for x in last if x != ln])
        name.append(ln)
        qty = rng.randint(1, 12)
        if i in negative:
            qty = -qty
        if i in zero:
            qty = 0
        cents = rng.randint(199, 24999)
        form = i % 3
        if form == 0:
            price = "%d.%02d" % divmod(cents, 100)
        elif form == 1:
            price = "%d.%d" % (cents // 100, (cents // 10) % 10)
        else:
            price = "%d" % (cents // 100)
        date = "%02d/%02d/%d" % (rng.randint(1, 12), rng.randint(1, 28), rng.choice([2025, 2026]))
        code = lower.get(i) or unknown.get(i) or rng.choice("SPCRH")
        fields = ["ORD-%05d" % (10017 + i * 7), " ".join(name), str(qty), price, date, code]
        if i in spaced:
            fields = [(" " + x + "  ") if k % 2 == 0 else ("  " + x) for k, x in enumerate(fields)]
        lines.append("|".join(fields))
    expected = [t1_expected(x) for x in lines]
    # the worked examples in the brief must obey the same function
    for raw, want in [
        ("ORD-90001|Dana R. Whitfield|3|19.99|03/07/2026|S", '"total":"59.97"'),
        ("ORD-90002| Li Wei |-2|5.5|12/01/2025|c", '"total":"-11.00"'),
        ("ORD-90003|Mary Ann K. Lopez-Diaz|1|40|01/15/2026|X", '"middle":"Ann K"'),
    ]:
        got = json.dumps(t1_expected(raw), separators=(",", ":"))
        assert want in got and got in T1_BRIEF, "worked example disagrees with the key: " + got
    write(os.path.join(FIX, "t1", "input.txt"), "\n".join(lines) + "\n")
    write(os.path.join(KEYS, "t1_expected.jsonl"),
          "# " + CANARY + "\n" + "\n".join(json.dumps(e) for e in expected) + "\n")
    return {"records": len(lines)}


# --------------------------------------------------------------------------- T2
SERVICES = ["auth", "payments", "billing", "search", "gateway", "inventory", "notify", "reports"]
PREFIX = {"auth": "auth", "payments": "pay", "billing": "bill", "search": "srch",
          "gateway": "gw", "inventory": "inv", "notify": "ntf", "reports": "rpt"}


def build_t2(rng):
    N = 2400
    used = set()

    def req():
        while True:
            r = "%06x" % rng.randrange(16 ** 6)
            if r not in used:
                used.add(r)
                return r

    def node(svc):
        return "%s-%d" % (PREFIX[svc], rng.randint(1, 4))

    def background(svc):
        roll = rng.random()
        err_w = 0.115 if svc == "gateway" else 0.06
        if roll < 0.0035:
            sev, msg = "CRITICAL", rng.choice(["service unavailable", "data store unreachable"])
        elif roll < 0.0035 + err_w:
            sev = "ERROR"
            opts = ["upstream timeout after %dms" % rng.randint(800, 9000),
                    "connection reset by peer", "failed to parse payload"]
            if svc == "payments":
                opts.append("ledger write timeout after %dms" % rng.randint(1000, 5000))
            if svc == "billing":
                opts.append("invoice render failed")
            msg = rng.choice(opts)
        elif roll < 0.30:
            sev = "WARN"
            msg = rng.choice(["slow query took %dms" % rng.randint(400, 6000),
                              "retrying upstream call attempt=%d" % rng.randint(2, 5),
                              "queue depth high depth=%d" % rng.randint(200, 4000)])
        else:
            sev = "INFO"
            msg = rng.choice(["request completed in %dms" % rng.randint(3, 900), "health check ok",
                              "cache refresh complete", "connection pool size=%d" % rng.randint(4, 64),
                              "scheduled job finished"])
        return sev, msg

    rows = []
    t = 0
    for _ in range(N):
        svc = rng.choice(SERVICES)
        sev, msg = background(svc)
        t += rng.randint(40, 160)
        rows.append({"svc": svc, "sev": sev, "node": node(svc), "msg": msg, "t": t})

    def stamp(sec):
        day = 13 + sec // 86400
        s = sec % 86400
        return "2026-03-%02dT%02d:%02d:%02dZ" % (day, s // 3600, (s % 3600) // 60, s % 60)

    def day_of(i):
        return 13 + rows[i]["t"] // 86400

    # Planted entries never overwrite one another: every index is handed out once.
    taken = set()

    def take(k, lo=60, hi=N - 60, day=None):
        pool = [i for i in range(lo, hi) if i not in taken and (day is None or day_of(i) == day)]
        got = sorted(rng.sample(pool, k))
        taken.update(got)
        return got

    def plant(idx, svc, sev, msg, nd=None):
        rows[idx].update({"svc": svc, "sev": sev, "node": nd or node(svc), "msg": msg})

    # disk-pressure warnings, with one node clearly ahead
    for idx in take(46):
        plant(idx, rng.choice(SERVICES), "WARN", "disk pressure at %d%%" % rng.randint(81, 97))
    hot = "inv-3"
    for idx in take(17):
        plant(idx, "inventory", "WARN", "disk pressure at %d%%" % rng.randint(88, 99), hot)

    # one service clearly ahead on ERROR volume, planted rather than left to the draw
    for idx in take(26):
        plant(idx, "gateway", "ERROR", "upstream timeout after %dms" % rng.randint(800, 9000))

    # deploys and rollbacks; exactly one rollback belongs to search
    spots = take(14, 100, N - 100)
    plant(spots[0], "search", "INFO", "deploy started version=4.11.3")
    plant(spots[1], "billing", "INFO", "deploy started version=2.8.0")
    plant(spots[2], "billing", "WARN", "rollback initiated from=2.8.0 to=2.7.4 reason=migration_lock_timeout")
    plant(spots[3], "search", "INFO", "deploy finished version=4.11.3")
    plant(spots[4], "search", "INFO", "deploy started version=4.12.0")
    plant(spots[5], "gateway", "INFO", "deploy started version=9.1.0")
    plant(spots[6], "search", "WARN", "rollback initiated from=4.12.0 to=4.11.3 reason=p99_latency_regression")
    plant(spots[7], "gateway", "WARN", "rollback initiated from=9.1.0 to=9.0.6 reason=error_budget_burn")
    plant(spots[8], "search", "INFO", "deploy started version=4.12.1")
    plant(spots[9], "auth", "INFO", "deploy started version=7.3.0")
    plant(spots[10], "auth", "WARN", "rollback initiated from=7.3.0 to=7.2.9 reason=session_store_errors")
    plant(spots[11], "search", "INFO", "deploy finished version=4.12.1")
    plant(spots[12], "payments", "INFO", "deploy started version=3.0.0")
    plant(spots[13], "payments", "INFO", "deploy finished version=3.0.0")

    # config changes; gateway max_connections changes three times, with distractors
    cfg = take(8, 100, N - 100)
    plant(cfg[0], "gateway", "INFO", "config changed key=max_connections old=512 new=768")
    plant(cfg[1], "search", "INFO", "config changed key=max_connections old=200 new=260")
    plant(cfg[2], "gateway", "INFO", "config changed key=idle_timeout_s old=60 new=45")
    plant(cfg[3], "gateway", "INFO", "config changed key=max_connections old=768 new=1024")
    plant(cfg[4], "billing", "INFO", "config changed key=max_connections old=64 new=96")
    plant(cfg[5], "gateway", "INFO", "config changed key=max_connections old=1024 new=896")
    plant(cfg[6], "gateway", "INFO", "config changed key=retry_budget old=3 new=5")
    plant(cfg[7], "auth", "INFO", "config changed key=max_connections old=128 new=1536")

    # the one payments CRITICAL that mentions the ledger
    plant(take(1, 200, N - 200)[0], "payments", "CRITICAL", "ledger checksum mismatch on shard 7")

    # auth token-cache warnings on every day, plus two entries on the 15th that match
    # the phrase but not the question: wrong severity, and wrong service. Both are
    # placed BEFORE the first real match, so a careless grep returns one of them.
    for d, k in ((13, 3), (14, 4)):
        for idx in take(k, day=d):
            plant(idx, "auth", "WARN", "token cache nearing capacity")
    first15 = min(i for i in range(N) if day_of(i) == 15)
    real15 = take(4, lo=first15 + 40, day=15)
    for idx in real15:
        plant(idx, "auth", "WARN", "token cache nearing capacity")
    decoys = take(2, lo=first15 + 2, hi=real15[0], day=15)
    plant(decoys[0], "auth", "INFO", "token cache refreshed")
    plant(decoys[1], "gateway", "WARN", "token cache miss rate high")

    # req ids: unique everywhere, except billing ERRORs which reuse a small pool
    pool = [req() for _ in range(9)]
    for r in rows:
        if r["svc"] == "billing" and r["sev"] == "ERROR":
            r["req"] = rng.choice(pool)
        else:
            r["req"] = req()

    lines = ['%s [%s] %s req=%s node=%s msg="%s"' % (stamp(r["t"]), r["svc"], r["sev"], r["req"], r["node"], r["msg"])
             for r in rows]

    # ---- answers, computed from the rows as written ----
    def count(pred):
        return sum(1 for r in rows if pred(r))

    by_err = {s: count(lambda r, s=s: r["svc"] == s and r["sev"] == "ERROR") for s in SERVICES}
    rank = sorted(by_err.items(), key=lambda kv: -kv[1])
    assert rank[0][1] - rank[1][1] >= 8, "q2 has no clear winner: %r" % (rank[:3],)

    led = [r for r in rows if r["svc"] == "payments" and r["sev"] == "CRITICAL" and "ledger" in r["msg"]]
    assert len(led) == 1, "q3 is not unique"
    assert count(lambda r: r["svc"] == "payments" and r["sev"] == "ERROR" and "ledger" in r["msg"]) >= 3, "q3 has no distractors"

    rb = [r for r in rows if r["svc"] == "search" and "rollback initiated" in r["msg"]]
    assert len(rb) == 1
    kv = dict(p.split("=", 1) for p in rb[0]["msg"].split() if "=" in p)

    tc = [r for r in rows if r["svc"] == "auth" and r["sev"] == "WARN" and "token cache" in r["msg"]]
    on15 = [r for r in tc if stamp(r["t"]).startswith("2026-03-15")]
    assert len(on15) >= 2 and len(tc) > len(on15), "q6 needs several on the 15th and some earlier"
    any15 = [r for r in rows if "token cache" in r["msg"] and stamp(r["t"]).startswith("2026-03-15")]
    assert any15[0] is not on15[0] and any15[1] is not on15[0], "q6 decoys must precede the real answer"

    dp = {}
    for r in rows:
        if "disk pressure" in r["msg"]:
            dp[r["node"]] = dp.get(r["node"], 0) + 1
    drank = sorted(dp.items(), key=lambda kv2: -kv2[1])
    assert drank[0][0] == hot and drank[0][1] - drank[1][1] >= 4, "q7 has no clear winner: %r" % (drank[:3],)

    gw = [r for r in rows if r["svc"] == "gateway" and "key=max_connections" in r["msg"]]
    assert len(gw) == 3
    last_new = int(gw[-1]["msg"].rsplit("new=", 1)[1])
    assert last_new != max(int(r["msg"].rsplit("new=", 1)[1]) for r in rows if "key=max_connections" in r["msg"]), \
        "q8 must not be answerable by taking the largest value"

    # positional anchor: an ordinary line whose successor is specific
    anchor = None
    for i in range(900, N - 2):
        a, b = rows[i], rows[i + 1]
        if i in taken or (i + 1) in taken:
            continue
        if a["sev"] == "INFO" and b["sev"] in ("WARN", "ERROR") and any(ch.isdigit() for ch in b["msg"]):
            if sum(1 for r in rows if r["req"] == a["req"]) == 1:
                anchor = i
                break
    assert anchor is not None

    bill = [r["req"] for r in rows if r["svc"] == "billing" and r["sev"] == "ERROR"]
    assert len(set(bill)) < len(bill), "q10 distinct equals total; the question would be trivial"

    answers = {
        "q1": count(lambda r: r["sev"] == "CRITICAL"),
        "q2": rank[0][0],
        "q3": led[0]["req"],
        "q4": kv["to"],
        "q5": kv["reason"],
        "q6": stamp(on15[0]["t"]),
        "q7": hot,
        "q8": last_new,
        "q9": rows[anchor + 1]["msg"],
        "q10": len(set(bill)),
    }
    brief = T2_BRIEF.replace("<ANCHOR>", rows[anchor]["req"])
    text = "\n".join(lines) + "\n"
    write(os.path.join(FIX, "t2", "service.log"), text)
    write(os.path.join(KEYS, "t2_answers.json"), json.dumps({"_": CANARY, "answers": answers,
          "detail": {"errors_by_service": by_err, "disk_pressure_top": drank[:3],
                     "billing_error_total": len(bill), "anchor_line": anchor + 1}}, indent=1) + "\n")
    return {"lines": N, "chars": len(text), "approx_tokens": len(text) // 4, "brief": brief}


T2_BRIEF = """\
service.log in this directory is a service log, one entry per line:

  <timestamp> [<service>] <SEVERITY> req=<id> node=<node> msg="<message>"

Answer the ten questions below from the log. Use any method you like — reading, grep,
awk, a script. Each answer is graded by exact match.

q1  (integer) How many entries have severity CRITICAL?
q2  (string)  Which service has the most ERROR entries? Give the service name.
q3  (string)  Exactly one CRITICAL entry from service payments has a message mentioning
              "ledger". Give its req id.
q4  (string)  One deploy of service search was rolled back. Which version was it rolled
              back TO?
q5  (string)  What reason= value was recorded on that search rollback?
q6  (string)  Give the timestamp of the earliest WARN entry from service auth on
              2026-03-15 whose message mentions "token cache".
q7  (string)  Which node logged the most entries whose message mentions "disk pressure"?
              Give the node name.
q8  (integer) Service gateway had its max_connections setting changed more than once.
              What is the new= value of the LAST such change?
q9  (string)  Give the full msg text, without the surrounding quotes, of the entry on the
              line immediately after the entry with req=<ANCHOR>.
q10 (integer) How many DISTINCT req ids appear among ERROR entries from service billing?
"""

# --------------------------------------------------------------------------- T3
T3_BRIEF = """\
Review ledger.py against SPEC.md, both in this directory. SPEC.md is the contract: where
the code's behaviour contradicts a numbered clause, that is a defect.

Report every defect you can demonstrate. For each one give the line number in ledger.py
where the faulty code is, a one-sentence description, and the number of the SPEC clause
it violates.

Report only behaviour that contradicts a numbered clause — not style, naming, performance
or features the spec does not ask for. A report padded with speculation is worse than a
short one. You may run Python to confirm a suspicion. Do not modify ledger.py or SPEC.md;
copy the file if you want to experiment.
"""


def build_t3():
    ref = open(os.path.join(SRC, "ledger_ok.py")).read()
    tests = load("ledger_tests", os.path.join(SRC, "ledger_tests.py"))
    mutmod = load("ledger_mutations", os.path.join(SRC, "ledger_mutations.py"))
    muts, keywords, also = mutmod.MUTATIONS, mutmod.KEYWORDS, mutmod.ALSO
    assert set(keywords) == set(m[0] for m in muts), "every seeded defect needs a keyword list"

    def failures(src):
        m = load("ledger", src=src)
        out = []
        for t in tests.ALL:
            try:
                t(m)
            except Exception:
                out.append(t.__name__)
        return out

    assert not failures(ref), "the reference violates its own spec"
    buggy = ref
    for bid, _d, _c, old, new, _desc in muts:
        assert ref.count(old) == 1, bid + ": old snippet is not unique in the reference"
        assert failures(ref.replace(old, new)), bid + ": mutation is not observable"
        buggy = buggy.replace(old, new)
    # strip the canary line from what agents see
    public = "\n".join(l for l in buggy.split("\n") if CANARY not in l)
    assert CANARY not in public
    bugs = []
    for bid, diff, clause, old, new, desc in muts:
        # the line that actually differs inside the replaced snippet
        o, n = old.split("\n"), new.split("\n")
        delta = next(i for i, (a, b) in enumerate(zip(o, n)) if a != b)
        changed = n[delta]
        # a snippet may be part of a line, so locate by offset and then confirm the
        # line found really carries the changed text
        assert public.count(new) == 1, bid + ": mutated snippet is not unique"
        start = public.index(new)
        line = public.count("\n", 0, start) + 1 + delta
        assert changed.strip() in public.split("\n")[line - 1], bid + ": could not locate the mutated line"
        extra = also.get(bid, {})
        bugs.append({"id": bid, "difficulty": diff, "clause": clause, "line": line, "desc": desc,
                     "clauses": sorted(set([clause] + extra.get("clauses", []))),
                     "also_functions": extra.get("functions", []),
                     "keywords": keywords[bid]})
    write(os.path.join(FIX, "t3", "ledger.py"), public)
    shutil.copy(os.path.join(SRC, "ledger_SPEC.md"), os.path.join(FIX, "t3", "SPEC.md"))
    write(os.path.join(KEYS, "t3_bugs.json"), json.dumps({"_": CANARY, "bugs": bugs}, indent=1) + "\n")
    return {"bugs": len(bugs), "lines": public.count("\n")}


# --------------------------------------------------------------------------- T4
T4_BRIEF = """\
Implement solution.py in this directory exactly as SPEC.md (also in this directory)
specifies. Standard library only. Hidden tests that you cannot see check every numbered
clause, so verify your own work before returning.
"""


def build_t4():
    sol = load("solution", os.path.join(SRC, "solution_ok.py"))
    ht = load("hidden_tests", os.path.join(SRC, "hidden_tests.py"))
    res = ht.score(sol)
    assert all(ok for _n, _c, ok in res), "the reference fails its own hidden tests"
    shutil.copy(os.path.join(SRC, "t4_SPEC.md"), os.path.join(FIX, "t4", "SPEC.md"))
    return {"hidden_tests": len(res)}


def main():
    for d in (FIX, KEYS):
        if os.path.isdir(d):
            shutil.rmtree(d)
    for t in ("t1", "t2", "t3", "t4"):
        os.makedirs(os.path.join(FIX, t))
    os.makedirs(KEYS)
    rng = random.Random(SEED)
    info = {"t1": build_t1(rng)}
    t2 = build_t2(random.Random(SEED + 1))
    t2_brief = t2.pop("brief")
    info["t2"] = t2
    info["t3"] = build_t3()
    info["t4"] = build_t4()
    briefs = {"t1": T1_BRIEF, "t2": t2_brief, "t3": T3_BRIEF, "t4": T4_BRIEF}
    write(os.path.join(HERE, "briefs.json"), json.dumps(briefs, indent=1) + "\n")
    # nothing an agent sees may carry the canary
    for root, _dirs, files in os.walk(FIX):
        for f in files:
            with open(os.path.join(root, f)) as fh:
                assert CANARY not in fh.read(), "canary leaked into " + f
    assert CANARY not in json.dumps(briefs)
    print(json.dumps(info, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
