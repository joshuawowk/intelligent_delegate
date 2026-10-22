#!/usr/bin/env python3
"""Audit where a Claude Code session's money and time went: orchestrator vs subagents.

Why this exists
---------------
The skill's routing rules were tuned on subagent tiering. The first real session
audited after 0.4.0 shipped (2026-10-22, a 50-minute build in an Opus 5.5 / xhigh
session) tiered every subagent correctly — and the orchestrator was still 76% of
the bill: $16.47 of Opus against $5.29 of Sonnet for the agents that did the
building. Its ~395K-token context was re-read on every request, and every
background-agent completion woke it for another one. That is invisible from inside
the session, so this script makes it visible after the fact.

What it reads
-------------
A main transcript ``~/.claude/projects/<cwd-slug>/<session-id>.jsonl`` and, beside
it, ``<session-id>/subagents/agent-*.jsonl`` with their ``.meta.json``. Assistant
records repeat one API response once per content block with identical usage, so
usage is counted once per ``message.id``.

What it prints
--------------
Spend and requests per model; orchestrator vs subagent share; each subagent's
tier, model, effort, requests, wall time and estimated cost; how many orchestrator
turns were started by a background-task notification and what one costs at the
current context size; and findings, each tied to a rule in skills/delegate.

Costs are ESTIMATES at first-party list prices (the PRICES table, read
2026-10-22 from the prompt-caching pricing table; fast mode priced from the usage
record's "speed"). They ignore batch, data residency and the advisor's own
server-side usage, which the transcript does not itemise. Claude Code's own
per-model ``costUSD`` (stream-json ``result`` events, ``claude -p
--output-format json``) is authoritative where you have it.

Usage
-----
    delegation_audit.py                      # newest transcript under ~/.claude/projects
    delegation_audit.py <session-id>         # find it by id
    delegation_audit.py path/to/session.jsonl [--json]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

# $/MTok: input, 5m cache write, 1h cache write, cache read, output.
# Source: platform.claude.com/docs/en/build-with-claude/prompt-caching (pricing table),
# fetched 2026-10-22. Cache reads are 0.05x input on Opus 5.5 and Sonnet 5.5 and
# 0.025x on Fable 5.1, not the usual 0.1x.
PRICES = {
    "claude-fable-5-1": (10.0, 12.5, 20.0, 0.25, 50.0),
    "claude-opus-5-5": (4.0, 5.0, 8.0, 0.20, 20.0),
    "claude-sonnet-5-5": (2.0, 2.5, 4.0, 0.10, 10.0),
    "claude-haiku-5-5": (0.10, 0.125, 0.20, 0.01, 0.50),
    "claude-opus-5": (5.0, 6.25, 10.0, 0.50, 25.0),
    "claude-sonnet-5": (2.0, 2.5, 4.0, 0.20, 10.0),
    "claude-haiku-4-5": (1.0, 1.25, 2.0, 0.10, 5.0),
}
# Fast mode (usage "speed": "fast") is priced as a multiplier on every rate, cache rates
# included (fast-mode docs: caching multipliers "apply on top of fast mode pricing").
FAST_MULT = {"claude-opus-5-5": 2.0, "claude-opus-5": 2.0}
# Haiku 5.5 bills every rate 5x on a request whose prompt exceeds 100K tokens;
# cache reads and writes count toward that prompt length.
LONG_PROMPT = {"claude-haiku-5-5": (100_000, 5.0)}

# Thresholds behind the findings. Each is a judgement, stated so it can be argued with.
ORCH_SHARE_WARN = 0.50      # orchestrator above half the bill while subagents ran
ORCH_CTX_WARN = 150_000     # mean orchestrator prompt worth shrinking
REBUILD_FRACTION = 0.5      # a request that writes >half its prompt rebuilt its cache
REBUILD_MIN_TOKENS = 20_000  # ...and only when that prompt is big enough to matter

# One per finished background agent; its "<agent-message>" hand-back travels with it.
NOTIFICATION_RE = re.compile(r"<task-notification>")


def canonical(model: str | None) -> str:
    if not model:
        return "unknown"
    m = re.sub(r"\[.*?\]$", "", model)          # drop "[1m]"-style suffixes
    m = re.sub(r"-\d{8}$", "", m)               # drop dated snapshot suffixes
    return m


def cost_of(model: str, u: dict) -> float | None:
    p = PRICES.get(canonical(model))
    if p is None:
        return None
    inp, w5, w1h, rd, out = p
    cc = u.get("cache_creation") or {}
    c5 = cc.get("ephemeral_5m_input_tokens")
    c1 = cc.get("ephemeral_1h_input_tokens")
    total_write = u.get("cache_creation_input_tokens", 0) or 0
    if c5 is None and c1 is None:
        c5, c1 = total_write, 0                 # no split recorded: assume the 5m default
    c5, c1 = c5 or 0, c1 or 0
    prompt = (u.get("input_tokens", 0) or 0) + total_write + (u.get("cache_read_input_tokens", 0) or 0)
    mult = FAST_MULT.get(canonical(model), 1.0) if u.get("speed") == "fast" else 1.0
    lp = LONG_PROMPT.get(canonical(model))
    if lp and prompt > lp[0]:
        mult *= lp[1]
    return mult * (
        (u.get("input_tokens", 0) or 0) * inp
        + c5 * w5
        + c1 * w1h
        + (u.get("cache_read_input_tokens", 0) or 0) * rd
        + (u.get("output_tokens", 0) or 0) * out
    ) / 1e6


def ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Claude Code writes UTC with a Z; read a bare timestamp as UTC too, so a stray one
    # cannot make the aware/naive comparison in add_time() raise.
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


class Stream:
    """One transcript: the main loop or one subagent."""

    def __init__(self, name: str):
        self.name = name
        self.requests: dict[str, dict] = {}     # message.id -> request summary
        self.first = None
        self.last = None
        self.efforts = set()
        self.advisor = set()
        self.tool_uses: list[dict] = []
        self.notifications = 0

    def add_time(self, t):
        if t is None:
            return
        self.first = t if self.first is None or t < self.first else self.first
        self.last = t if self.last is None or t > self.last else self.last

    @property
    def wall_s(self) -> float:
        return (self.last - self.first).total_seconds() if self.first and self.last else 0.0

    def totals(self) -> dict:
        t = defaultdict(float)
        for r in self.requests.values():
            for k in ("input", "write", "read", "output", "cost"):
                t[k] += r[k] or 0
            t["requests"] += 1
        return t

    def models(self) -> set:
        return {r["model"] for r in self.requests.values()}


def read_stream(path: str, name: str) -> Stream:
    s = Stream(name)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = ts(r.get("timestamp"))
            kind = r.get("type")
            if kind == "assistant":
                s.add_time(t)
                m = r.get("message") or {}
                if r.get("effort"):
                    s.efforts.add(r["effort"])
                if r.get("advisorModel"):
                    s.advisor.add(canonical(r["advisorModel"]))
                for c in m.get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "tool_use":
                        s.tool_uses.append({"name": c.get("name"), "input": c.get("input") or {}, "id": c.get("id")})
                mid = m.get("id")
                u = m.get("usage")
                if not mid or not u or mid in s.requests:
                    continue
                model = canonical(m.get("model"))
                cc = u.get("cache_creation") or {}
                write = u.get("cache_creation_input_tokens", 0) or 0
                read = u.get("cache_read_input_tokens", 0) or 0
                inp = u.get("input_tokens", 0) or 0
                s.requests[mid] = {
                    "model": model,
                    "input": inp,
                    "write": write,
                    "write_1h": cc.get("ephemeral_1h_input_tokens") or 0,
                    "read": read,
                    "output": u.get("output_tokens", 0) or 0,
                    "prompt": inp + write + read,
                    "cost": cost_of(model, u),
                    "t": t,
                }
            elif kind == "user":
                s.add_time(t)
            elif kind == "queue-operation" and r.get("operation") == "enqueue":
                if NOTIFICATION_RE.search(str(r.get("content", ""))):
                    s.notifications += 1
    return s


def find_transcript(arg: str | None) -> str:
    root = os.path.expanduser("~/.claude/projects")
    if arg and os.path.isfile(arg):
        return arg
    pattern = os.path.join(root, "*", (arg + ".jsonl") if arg else "*.jsonl")
    hits = [p for p in glob.glob(pattern) if os.path.isfile(p)]
    if not hits:
        sys.exit("no transcript found for %r under %s" % (arg, root))
    return max(hits, key=os.path.getmtime)


def load(path: str):
    main = read_stream(path, "orchestrator")
    base = path[:-len(".jsonl")]
    subs = []
    for p in sorted(glob.glob(os.path.join(base, "**", "agent-*.jsonl"), recursive=True)):
        meta = {}
        mp = p[:-len(".jsonl")] + ".meta.json"
        if os.path.isfile(mp):
            try:
                meta = json.load(open(mp, encoding="utf-8"))
            except ValueError:
                meta = {}
        s = read_stream(p, os.path.basename(p)[len("agent-"):-len(".jsonl")])
        s.meta = meta
        subs.append(s)
    return main, subs


def fmt_tok(n: float) -> str:
    n = float(n)
    if n >= 1e6:
        return "%.1fM" % (n / 1e6)
    if n >= 1e3:
        return "%.0fK" % (n / 1e3)
    return "%d" % n


def fmt_usd(x) -> str:
    return "  n/a" if x is None else "$%.2f" % x


def analyse(main: Stream, subs: list) -> dict:
    session_models = main.models()
    session_model = max(session_models, key=lambda m: sum(1 for r in main.requests.values() if r["model"] == m)) if session_models else "unknown"
    session_effort = sorted(main.efforts)[-1] if main.efforts else None
    mt = main.totals()
    sub_rows = []
    for s in subs:
        t = s.totals()
        meta = getattr(s, "meta", {})
        sub_rows.append({
            "id": s.name,
            "agentType": meta.get("agentType") or "?",
            "description": meta.get("description") or "",
            "background": meta.get("requestShape") == "background",
            "models": sorted(s.models()),
            "effort": sorted(s.efforts),
            "advisor": sorted(s.advisor),
            "requests": int(t["requests"]),
            "wall_s": round(s.wall_s, 1),
            "read": int(t["read"]),
            "write": int(t["write"]),
            "output": int(t["output"]),
            "cost": round(t["cost"], 4),
        })
    sub_cost = sum(r["cost"] for r in sub_rows)
    total = mt["cost"] + sub_cost

    by_model = defaultdict(lambda: defaultdict(float))
    for s in [main] + subs:
        for r in s.requests.values():
            b = by_model[r["model"]]
            b["requests"] += 1
            for k in ("input", "write", "read", "output"):
                b[k] += r[k]
            b["cost"] += r["cost"] or 0          # rendered as n/a below when any is unpriced
            if r["cost"] is None:
                b["unpriced"] += 1

    prompts = [r["prompt"] for r in main.requests.values()]
    mean_ctx = sum(prompts) / len(prompts) if prompts else 0
    last_ctx = prompts[-1] if prompts else 0
    p = PRICES.get(session_model)
    wake_cost = (last_ctx * p[3] / 1e6) if p else None

    # The first request of a session always writes its whole prompt: that is the initial
    # build, not a rebuild, so only later requests count.
    ordered = list(main.requests.values())      # file order is request order
    rebuilds = [r for r in ordered[1:]
                if r["prompt"] >= REBUILD_MIN_TOKENS and r["write"] > REBUILD_FRACTION * r["prompt"]]
    rebuild_cost = 0.0
    if p:
        for r in rebuilds:
            w1 = min(r["write_1h"], r["write"])
            paid = w1 * p[2] + (r["write"] - w1) * p[1]
            rebuild_cost += (paid - r["write"] * p[3]) / 1e6   # paid as a write instead of a read

    agent_calls = [u for u in main.tool_uses if u["name"] in ("Agent", "Task")]
    workflow_calls = [u for u in main.tool_uses if u["name"] == "Workflow"]

    findings = []
    unpriced = {m: int(d["unpriced"]) for m, d in by_model.items() if d.get("unpriced")}
    if unpriced:
        findings.append((
            "unpriced-model",
            "%d requests ran on models with no price in PRICES (%s). Their cost is left out of every total "
            "and share above, so read the shares as approximate."
            % (sum(unpriced.values()), ", ".join("%s x%d" % kv for kv in sorted(unpriced.items())))))
    if subs and total and mt["cost"] / total > ORCH_SHARE_WARN:
        findings.append((
            "orchestrator-heavy",
            "The orchestrator was %.0f%% of estimated spend (%s of %s) while %d subagents did the delegated work. "
            "Mean orchestrator prompt %s tokens over %d requests. Shrink what the orchestrator re-reads "
            "(SKILL.md: 'The orchestrator is a cost centre')."
            % (100 * mt["cost"] / total, fmt_usd(mt["cost"]), fmt_usd(total), len(subs), fmt_tok(mean_ctx), int(mt["requests"]))))
    if mean_ctx > ORCH_CTX_WARN:
        findings.append((
            "large-orchestrator-context",
            "Mean orchestrator prompt %s tokens: every request re-reads it. /compact with a focus, or /clear and "
            "re-brief from a state file, between phases." % fmt_tok(mean_ctx)))
    if main.notifications:
        findings.append((
            "notification-wakeups",
            "%d background-task notifications reached the orchestrator; each one starts a turn that re-reads the "
            "context (%s now, about %s per request at %s's cache-read rate before any output). A Workflow reports "
            "once at the end." % (main.notifications, fmt_tok(last_ctx), fmt_usd(wake_cost), session_model)))
    if rebuilds:
        findings.append((
            "cache-rebuilds",
            "%d orchestrator requests rewrote more than half of their prompt to cache (a model or tool-set "
            "change, a compaction, or a TTL lapse), about %s more than reading it." % (len(rebuilds), fmt_usd(rebuild_cost))))
    untiered = [r for r in sub_rows if r["agentType"] in ("?", "general-purpose", "workflow-subagent")]
    on_session = [r for r in sub_rows if session_model in r["models"]]
    if untiered:
        findings.append((
            "untiered-subagents",
            "%d subagents carried no tiered definition (%s). They inherit the session's model and effort unless the "
            "call named both." % (len(untiered), ", ".join(sorted({r["agentType"] for r in untiered})))))
    if on_session and len(on_session) >= 3:
        findings.append((
            "session-model-fanout",
            "%d of %d subagents ran on the session model (%s). For a fan-out, start at the pinned-Sonnet rung "
            "(SKILL.md anti-pattern 14)." % (len(on_session), len(sub_rows), session_model)))
    inherited = [r for r in sub_rows if session_effort and r["effort"] == [session_effort]
                 and r["agentType"] not in ("intelligent-delegate:builder", "intelligent-delegate:reviewer")]
    if inherited and session_effort in ("xhigh", "max"):
        findings.append((
            "inherited-effort",
            "%d subagents ran at the session's %s effort. Unless that was chosen, an effort was left unset "
            "(SKILL.md anti-pattern 16)." % (len(inherited), session_effort)))
    adv = [r for r in sub_rows for a in r["advisor"]
           if PRICES.get(a) and r["models"] and PRICES.get(r["models"][0]) and PRICES[a][4] > PRICES[r["models"][0]][4]]
    if adv:
        findings.append((
            "advisor-above-tier",
            "%d subagents had an advisor (%s) pricier than their own model attached. A consult bills at the "
            "advisor's rates; /advisor off for cheap fan-outs." % (len(adv), ", ".join(sorted({a for r in adv for a in r["advisor"]})))))

    return {
        "session_model": session_model,
        "session_effort": session_effort,
        "wall_s": round(main.wall_s, 1),
        "estimated_total_usd": round(total, 4),
        "orchestrator": {
            "requests": int(mt["requests"]),
            "read": int(mt["read"]),
            "write": int(mt["write"]),
            "output": int(mt["output"]),
            "cost": round(mt["cost"], 4),
            "share": round(mt["cost"] / total, 4) if total else None,
            "mean_prompt": int(mean_ctx),
            "last_prompt": int(last_ctx),
            "notifications": main.notifications,
            "cost_per_wakeup_read": round(wake_cost, 4) if wake_cost is not None else None,
            "cache_rebuilds": len(rebuilds),
            "agent_calls": len(agent_calls),
            "workflow_calls": len(workflow_calls),
        },
        "subagents": sub_rows,
        "by_model": {m: {k: (None if k == "cost" and d.get("unpriced") else round(v, 4) if k == "cost" else int(v))
                         for k, v in d.items()} for m, d in by_model.items()},
        "findings": [{"code": c, "detail": d} for c, d in findings],
    }


def render(path: str, a: dict) -> str:
    o = a["orchestrator"]
    lines = [
        "Session  %s" % os.path.basename(path),
        "Model    %s @ %s    wall %.0f min    estimated %s at list prices" % (
            a["session_model"], a["session_effort"] or "?", a["wall_s"] / 60, fmt_usd(a["estimated_total_usd"])),
        "",
        "%-22s %8s %8s %8s %8s %9s" % ("by model", "requests", "read", "write", "output", "est $"),
    ]
    for m, d in sorted(a["by_model"].items(), key=lambda kv: -(kv[1]["cost"] or 0)):
        lines.append("%-22s %8d %8s %8s %8s %9s" % (m, d["requests"], fmt_tok(d["read"]), fmt_tok(d["write"]), fmt_tok(d["output"]), fmt_usd(d["cost"])))
    lines += [
        "",
        "orchestrator  %s (%s of spend)  %d requests  mean prompt %s  last %s" % (
            fmt_usd(o["cost"]), "%.0f%%" % (100 * o["share"]) if o["share"] is not None else "n/a",
            o["requests"], fmt_tok(o["mean_prompt"]), fmt_tok(o["last_prompt"])),
        "              %d Agent calls, %d Workflow calls, %d background notifications, %d cache rebuilds" % (
            o["agent_calls"], o["workflow_calls"], o["notifications"], o["cache_rebuilds"]),
    ]
    if a["subagents"]:
        lines += ["", "%-34s %-18s %-7s %5s %7s %8s  %s" % ("subagent tier", "model", "effort", "reqs", "wall s", "est $", "description")]
        for r in sorted(a["subagents"], key=lambda r: -r["cost"]):
            lines.append("%-34s %-18s %-7s %5d %7.0f %8s  %s" % (
                r["agentType"][:34], ",".join(r["models"])[:18], ",".join(r["effort"])[:7], r["requests"],
                r["wall_s"], fmt_usd(r["cost"]), r["description"][:40]))
    lines += ["", "findings:" if a["findings"] else "findings: none"]
    for f in a["findings"]:
        lines.append("  [%s] %s" % (f["code"], f["detail"]))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", help="transcript path or session id (default: newest transcript)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = ap.parse_args(argv)
    path = find_transcript(args.target)
    main_s, subs = load(path)
    a = analyse(main_s, subs)
    print(json.dumps(a, indent=2, default=str) if args.json else render(path, a))
    return 0


if __name__ == "__main__":
    sys.exit(main())
