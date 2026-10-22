#!/usr/bin/env python3
"""Tests for delegation_audit.py. Run: python3 scripts/test_delegation_audit.py

Builds a small synthetic transcript in a temp dir — an Opus orchestrator, two Sonnet
subagents (one tiered, one untiered), two background notifications and one cache
rebuild — and checks the arithmetic and the findings against hand-computed values.
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import delegation_audit as da  # noqa: E402


def usage(inp=0, w5=0, w1=0, read=0, out=0):
    return {"input_tokens": inp, "cache_creation_input_tokens": w5 + w1,
            "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
            "cache_read_input_tokens": read, "output_tokens": out}


def asst(mid, model, u, t, effort="xhigh", content=None, advisor=None):
    r = {"type": "assistant", "timestamp": t, "effort": effort,
         "message": {"id": mid, "model": model, "usage": u, "content": content or [{"type": "text", "text": "x"}]}}
    if advisor:
        r["advisorModel"] = advisor
    return r


def build(tmp):
    main = os.path.join(tmp, "sess.jsonl")
    sub_dir = os.path.join(tmp, "sess", "subagents")
    os.makedirs(sub_dir)
    O, S = "claude-opus-5-5", "claude-sonnet-5-5"
    rows = [
        asst("m1", O, usage(inp=10, w1=200_000, out=1_000), "2026-10-22T00:00:00Z",
             content=[{"type": "tool_use", "name": "Agent", "id": "t1", "input": {"subagent_type": "intelligent-delegate:worker"}}]),
        # the same API response again, as a second content block: must not double count
        asst("m1", O, usage(inp=10, w1=200_000, out=1_000), "2026-10-22T00:00:01Z",
             content=[{"type": "tool_use", "name": "Agent", "id": "t2", "input": {}}]),
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-22T00:05:00Z",
         "content": "<agent-message from=\"a\">hand-back</agent-message>"},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-22T00:05:00Z",
         "content": "<task-notification><task-id>a</task-id></task-notification>"},
        {"type": "queue-operation", "operation": "enqueue", "timestamp": "2026-10-22T00:06:00Z",
         "content": "<task-notification><task-id>b</task-id></task-notification>"},
        asst("m2", O, usage(inp=5, read=200_000, w1=1_000, out=500), "2026-10-22T00:05:01Z"),
        # a rebuild: >half the prompt written again
        asst("m3", O, usage(inp=5, w5=150_000, read=60_000, out=500), "2026-10-22T00:10:00Z"),
    ]
    with open(main, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    for aid, meta, eff in (("a", {"agentType": "intelligent-delegate:worker", "description": "tiered", "requestShape": "background"}, "medium"),
                           ("b", {"agentType": "general-purpose", "description": "untiered"}, "xhigh")):
        with open(os.path.join(sub_dir, "agent-%s.jsonl" % aid), "w") as fh:
            fh.write(json.dumps(asst("s%s1" % aid, S, usage(inp=3, w5=10_000, out=2_000), "2026-10-22T00:01:00Z", effort=eff, advisor=O)) + "\n")
            fh.write(json.dumps(asst("s%s2" % aid, S, usage(inp=3, read=10_000, out=1_000), "2026-10-22T00:02:00Z", effort=eff, advisor=O)) + "\n")
        with open(os.path.join(sub_dir, "agent-%s.meta.json" % aid), "w") as fh:
            json.dump(meta, fh)
    return main


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


def main():
    fails = []
    with tempfile.TemporaryDirectory() as tmp:
        path = build(tmp)
        m, subs = da.load(path)
        a = da.analyse(m, subs)
        o = a["orchestrator"]

        # Opus 5.5: in 4, w5 5, w1h 8, read 0.20, out 20 ($/MTok)
        m1 = (10 * 4 + 200_000 * 8 + 1_000 * 20) / 1e6
        m2 = (5 * 4 + 200_000 * 0.20 + 1_000 * 8 + 500 * 20) / 1e6
        m3 = (5 * 4 + 150_000 * 5 + 60_000 * 0.20 + 500 * 20) / 1e6
        # Sonnet 5.5: in 2, w5 2.5, read 0.10, out 10
        sub = ((3 * 2 + 10_000 * 2.5 + 2_000 * 10) + (3 * 2 + 10_000 * 0.10 + 1_000 * 10)) / 1e6
        checks = [
            ("orchestrator requests dedupe by message id", o["requests"] == 3),
            ("orchestrator cost", close(o["cost"], round(m1 + m2 + m3, 4))),
            ("subagent cost each", all(close(r["cost"], round(sub, 4)) for r in a["subagents"])),
            ("total", close(a["estimated_total_usd"], round(m1 + m2 + m3 + 2 * sub, 4))),
            ("notifications count task-notifications only", o["notifications"] == 2),
            ("one cache rebuild", o["cache_rebuilds"] == 1),
            ("both Agent tool_use blocks counted", o["agent_calls"] == 2),
            ("session model and effort", a["session_model"] == "claude-opus-5-5" and a["session_effort"] == "xhigh"),
        ]
        codes = {f["code"] for f in a["findings"]}
        for code in ("orchestrator-heavy", "large-orchestrator-context", "notification-wakeups",
                     "cache-rebuilds", "untiered-subagents", "inherited-effort", "advisor-above-tier"):
            checks.append(("finding " + code, code in codes))
        checks.append(("no session-model-fanout finding: no subagent ran Opus", "session-model-fanout" not in codes))

        # Haiku 5.5 bills 5x on a request whose prompt passes 100K, cache tokens included
        hu = usage(inp=1_000, read=100_000, out=100)
        expect = 5 * (1_000 * 0.10 + 100_000 * 0.01 + 100 * 0.50) / 1e6
        checks.append(("Haiku long-prompt multiplier", close(da.cost_of("claude-haiku-5-5", hu), expect)))
        fu = dict(usage(inp=0, read=1_000_000, out=0), speed="fast")
        checks.append(("fast mode doubles Opus 5.5 cache reads", close(da.cost_of("claude-opus-5-5", fu), 0.40)))
        checks.append(("unknown model prices as None", da.cost_of("some-other-model", hu) is None))
        checks.append(("[1m] suffix is canonicalised", da.canonical("claude-opus-5-5[1m]") == "claude-opus-5-5"))

        text = da.render(path, a)
        checks.append(("render mentions every finding", all("[%s]" % c in text for c in codes)))

        for name, ok in checks:
            print("  %s  %s" % ("ok  " if ok else "FAIL", name))
            if not ok:
                fails.append(name)
    print("\n%d/%d passed" % (len(checks) - len(fails), len(checks)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
