#!/usr/bin/env python3
"""Tests for the tier-check hook. Run: python3 hooks/test_tier_check.py

Every case is here because it is a way the hook could be wrong in a direction that
matters. The expensive direction is a false DENY on a correct script — that gets the
hook switched off, after which it protects nothing — so most of these are allow cases.

The block marked REVIEWED is the set of false denies an `inspector`-tier review found
in the first implementation. They are kept as regression tests because every one of
them was a working repro, not a theory.
"""
import json
import os
import subprocess
import sys

HOOK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tier_check.py")


def run(payload):
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0, "hook must always exit 0, got %d: %s" % (
        p.returncode, p.stderr)
    out = p.stdout.strip()
    return json.loads(out) if out else None


def decision(payload):
    d = run(payload)
    if not d:
        return "allow"
    h = d.get("hookSpecificOutput")
    return (h.get("permissionDecision") or "allow+note") if h else "allow+note"


def wf(script):
    return {"tool_name": "Workflow", "tool_input": {"script": script}}


def note(payload):
    """The non-blocking systemMessage text, or '' when the hook said nothing."""
    d = run(payload)
    return (d or {}).get("systemMessage", "")


LEAK = "set no `effort`"


CASES = []


def case(name, payload, expect):
    CASES.append((name, payload, expect))


# --- the defect it exists to catch -----------------------------------------
case("bare agent() is denied", wf("""
export const meta = {name:'x', description:'y'}
const r = await agent('do a thing', {label:'a', phase:'P'})
"""), "deny")

case("agent() with no options argument at all is denied",
     wf("await agent('just a prompt')"), "deny")

case("one tiered + one bare is still denied", wf("""
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
const b = await agent('y', {label:'b'})
"""), "deny")

# --- correct scripts must pass ---------------------------------------------
case("fully tiered passes clean", wf("""
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:drafter'})
const b = await agent('y', {label:'b', agentType:'intelligent-delegate:inspector'})
"""), "allow")

case("inherit tier passes with a note", wf(
    "const a = await agent('x', {agentType:'intelligent-delegate:reviewer'})"),
    "allow+note")

case("no agent() at all passes", wf("""
export const meta = {name:'x', description:'y'}
return {ok: true}
"""), "allow")

# --- REVIEWED: false denies found by an inspector-tier review --------------
# Each of these was a reproduced false deny in the first implementation.
case("options hoisted into a variable are NOT denied", wf("""
const REVIEW = {agentType:'intelligent-delegate:inspector'}
await agent('x', REVIEW)
"""), "allow+note")

case("an object literal that spreads another is NOT denied", wf("""
const base = {agentType:'intelligent-delegate:worker'}
await agent('p', {...base, label:'a'})
"""), "allow+note")

case("a regex containing a backtick does not desync the scan", wf("""
const c = s.replace(/`/g, '')
const p = `never call agent() directly`
await agent(p, {agentType:'intelligent-delegate:inspector'})
"""), "allow")

case("a string nested in a ${} substitution is not a call site", wf("""
const p = `x ${ok ? 'use agent() here' : ''}`
await agent(p, {agentType:'intelligent-delegate:worker'})
"""), "allow")

case("a regex containing ) does not close the call early", wf(
    "await agent(s.replace(/\\)/g,''), {agentType:'intelligent-delegate:inspector'})"),
    "allow")

case("a nested template containing ) does not close the call early", wf(
    "await agent(`a ${ x ? `)` : '' } b`, {agentType:'intelligent-delegate:inspector'})"),
    "allow")

case("unbalanced parentheses are allowed, not denied", wf(
    "const a = await agent('x', {label:'a'}"), "allow+note")

# --- REVIEWED: missed denies -----------------------------------------------
case("agentType named inside a prompt does not count as tiering", wf(
    "await agent(`Please set agentType on every call`, {label:'x'})"), "deny")

case("agentType in a comment inside the options does not count", wf(
    "await agent('p', {label:'x' /* agentType later */})"), "deny")

case("a regex that hides a later untiered call is still caught", wf("""
const c = s.replace(/`/g, '')
await agent('x')
const q = `a`
"""), "deny")

case("the word reviewer in a prompt does not inflate the inherit count", wf(
    "await agent('act as reviewer', {agentType:'intelligent-delegate:inspector'})"),
    "allow")

# --- the escape hatch ------------------------------------------------------
case("waiver on the line above passes", wf("""
// untiered: needs a tool surface no shipped definition has
const a = await agent('x', {label:'a', effort:'max'})
"""), "allow+note")

case("waiver on the same line passes", wf(
    "const a = await agent('x', {effort:'max'}) // untiered: max effort\n"),
    "allow+note")

case("a block-comment waiver passes", wf("""
/* untiered: max effort needed here */
const a = await agent('x', {effort:'max'})
"""), "allow+note")

case("a waiver without the word untiered does NOT pass", wf("""
// this one is fine honestly, trust me
const a = await agent('x', {label:'a'})
"""), "deny")

case("a bare untiered: marker with no reason does NOT pass", wf("""
// untiered:
const a = await agent('x', {label:'a'})
"""), "deny")

case("a trailing waiver does not leak onto the next call", wf("""
await agent('a', {effort:'max'}) // untiered: needs max
await agent('b', {label:'b'})
"""), "deny")

case("a leading waiver does not leak onto the call after its own", wf("""
// untiered: needs max
await agent('a', {effort:'max'})
await agent('b', {label:'b'})
"""), "deny")

case("untiered: inside a prompt string does not waive", wf(
    "await agent('see http://x untiered: no', {label:'y'})"), "deny")

case("a waiver three lines up is out of range", wf("""
// untiered: reason


const a = await agent('x', {label:'a'})
"""), "deny")

# --- false-positive guards: agent( inside text is not a call site ---------
case("agent() discussed in a prompt string is not a call", wf("""
const a = await agent('Explain that agent(prompt, opts) takes an agentType.',
  {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

case("agent() in a template literal is not a call", wf("""
const brief = `Never write agent(prompt) with no agentType.
Always pass agent(p, {agentType}).`
const a = await agent(brief, {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

case("agent() in a line comment is not a call", wf("""
// bad: agent('x', {label:'y'})
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

case("agent() in a block comment is not a call", wf("""
/* historical: agent('x', {label:'y'}) ran untiered */
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

case("subagent( and obj.agent( are not agent(", wf("""
const a = subagent('x', {})
const b = runner.agent('y', {})
"""), "allow")

case("a ${} substitution inside a template IS code", wf(
    "const out = `${await agent('x', {label:'a'})}`"), "deny")

case("parens inside the prompt do not end the call early", wf("""
const a = await agent('see foo(bar) and baz(qux) for context',
  {label:'a', agentType:'intelligent-delegate:inspector'})
"""), "allow")

case("apostrophe in a comment does not desync the scan", wf("""
// this doesn't break the lexer
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

case("apostrophe in a template literal does not desync the scan", wf("""
const t = `it's fine`
const a = await agent('x', {label:'a'})
"""), "deny")

case("division is not read as a regex literal", wf("""
const n = 10 / 2 / 1
const a = await agent('x', {label:'a'})
"""), "deny")

case("a regex opening a false block comment does not desync", wf("""
const r = /\\/*/
await agent('x', {label:'a'})
"""), "deny")

case("a url in a string is not a comment", wf("""
const u = 'http://example.com/x'
const a = await agent('x', {label:'a'})
"""), "deny")

# --- fail-open behaviour ---------------------------------------------------
case("a non-Workflow tool is ignored", {"tool_name": "Bash",
     "tool_input": {"command": "agent('x', {})"}}, "allow")
case("a saved workflow invoked by name is ignored",
     {"tool_name": "Workflow", "tool_input": {"name": "review-changes"}}, "allow")
case("missing tool_input is ignored", {"tool_name": "Workflow"}, "allow")
case("a non-dict tool_input is ignored",
     {"tool_name": "Workflow", "tool_input": "oops"}, "allow")
case("a non-string script is ignored",
     {"tool_name": "Workflow", "tool_input": {"script": 42}}, "allow")
case("an unreadable scriptPath is ignored",
     {"tool_name": "Workflow", "tool_input": {"scriptPath": "/nonexistent/x.js"}},
     "allow")


# --- the effort leak: a waived call that names no effort runs at the session's -------
# These are note-only. Nothing here may ever turn an allow into a deny.
NOTE_CASES = [
    ("a waived call with a model but no effort is flagged", wf("""
// untiered: needs a tool surface no shipped tier has
const r = await agent('x', {model: 'haiku', label: 'a'})
"""), True),
    ("a waived call that sets effort is not", wf("""
// untiered: needs max effort, which no shipped tier pins
const r = await agent('x', {model: 'opus', effort: 'max', label: 'a'})
"""), False),
    ("shorthand `{effort}` counts as setting it", wf("""
const effort = 'low'
// untiered: effort chosen per item above
const r = await agent('x', {model: 'haiku', effort, label: 'a'})
"""), False),
    ("a waived call with no options at all is flagged", wf("""
// untiered: deliberately the session model at the session's effort
const r = await agent('just a prompt')
"""), True),
    ("a spread may carry effort, so it is not flagged", wf("""
// untiered: options assembled per item
const r = await agent('x', {...base, label: 'a'})
"""), False),
    ("options in a variable may carry effort, so it is not flagged", wf("""
// untiered: options assembled per item
const r = await agent('x', OPTS)
"""), False),
    ("`effortLevel` is a different key and does not count", wf("""
// untiered: bare opts
const r = await agent('x', {model: 'haiku', effortLevel: 'low'})
"""), True),
    ("the word effort inside the prompt string does not count", wf("""
// untiered: bare opts
const r = await agent('use high effort: think hard', {model: 'haiku'})
"""), True),
    ("a tiered call is never flagged: its definition pins the effort", wf("""
const r = await agent('x', {agentType: 'intelligent-delegate:mechanical', label: 'a'})
"""), False),
]


def run_env(payload, env):
    e = dict(os.environ)
    for k in ("CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_SUBAGENT_MODEL_FORCE",
              "CLAUDE_CODE_SUBAGENT_MODEL"):
        e.pop(k, None)
    e.update(env)
    p = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30, env=e)
    assert p.returncode == 0, p.stderr
    out = p.stdout.strip()
    return json.loads(out) if out else None


def ctx(d):
    """What reaches the model: hookSpecificOutput.additionalContext."""
    return ((d or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def agent(**ti):
    return {"tool_name": "Agent", "session_id": SID, "tool_input": dict(
        {"description": "d", "prompt": "p"}, **ti)}


SID = "test-%d" % os.getpid()

# (name, payload, env, check(d) -> bool). Notes never deny; these assert what reaches the model.
EXTRA_CASES = [
    ("Agent with no tier and no model gets a note the model can read",
     agent(), {}, lambda d: "names no tier" in ctx(d) and "permissionDecision" not in d["hookSpecificOutput"]),
    ("Agent naming general-purpose with no model gets the same note",
     agent(subagent_type="general-purpose"), {}, lambda d: "names no tier" in ctx(d)),
    ("Agent naming a tier is silent",
     agent(subagent_type="intelligent-delegate:inspector"), {}, lambda d: d is None),
    ("Agent with no tier but an explicit model is silent",
     agent(model="sonnet", effort="medium"), {}, lambda d: d is None),
    ("Explore is silent: it is a tier choice, if a session-model one",
     agent(subagent_type="Explore"), {}, lambda d: d is None),
    ("CLAUDE_CODE_EFFORT_LEVEL is reported on a tiered Agent call",
     dict(agent(subagent_type="intelligent-delegate:worker"), session_id=SID + "-e"),
     {"CLAUDE_CODE_EFFORT_LEVEL": "xhigh"}, lambda d: "CLAUDE_CODE_EFFORT_LEVEL=xhigh" in ctx(d)),
    ("...and only once per session",
     dict(agent(subagent_type="intelligent-delegate:worker"), session_id=SID + "-e"),
     {"CLAUDE_CODE_EFFORT_LEVEL": "xhigh"}, lambda d: d is None),
    ("SUBAGENT_MODEL_FORCE with a model is reported on a tiered workflow",
     dict(wf("const r = await agent('x', {agentType: 'intelligent-delegate:worker'})"), session_id=SID + "-f"),
     {"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1", "CLAUDE_CODE_SUBAGENT_MODEL": "haiku"},
     lambda d: "tiers collapse" in ctx(d)),
    ("FORCE without a model names nothing to collapse onto, so it is silent",
     dict(wf("const r = await agent('x', {agentType: 'intelligent-delegate:worker'})"), session_id=SID + "-g"),
     {"CLAUDE_CODE_SUBAGENT_MODEL_FORCE": "1"}, lambda d: d is None),
    ("an untiered workflow still denies, and carries the override note in the reason",
     dict(wf("const r = await agent('x', {label: 'a'})"), session_id=SID + "-h"),
     {"CLAUDE_CODE_EFFORT_LEVEL": "low"},
     lambda d: d["hookSpecificOutput"]["permissionDecision"] == "deny"
     and "CLAUDE_CODE_EFFORT_LEVEL=low" in d["hookSpecificOutput"]["permissionDecisionReason"]),
    ("workflow notes reach the model, not only the user",
     wf("// untiered: no definition fits\nconst r = await agent('x', {model: 'haiku'})"), {},
     lambda d: "set no `effort`" in ctx(d) and "set no `effort`" in d.get("systemMessage", "")),
]


def main():
    bad = []
    for payload, label in (("not json at all", "malformed stdin"),
                           ("[]", "non-dict json")):
        p = subprocess.run([sys.executable, HOOK], input=payload,
                           capture_output=True, text=True, timeout=30)
        if p.returncode != 0:
            bad.append("%s: exit %d, want 0" % (label, p.returncode))

    passed = 0
    for name, payload, expect in CASES:
        got = decision(payload)
        if got == expect:
            passed += 1
            print("  ok    %s" % name)
        else:
            bad.append("%s: got %s, want %s" % (name, got, expect))
            print("  FAIL  %s -> %s (want %s)" % (name, got, expect))

    for name, payload, env, check in EXTRA_CASES:
        try:
            ok = bool(check(run_env(payload, env)))
        except Exception as e:  # a shape the check did not expect is a failure
            ok = False
            name = "%s (%s: %s)" % (name, type(e).__name__, e)
        passed += ok
        print("  %s  %s" % ("ok  " if ok else "FAIL", name))
        if not ok:
            bad.append(name)

    total = len(CASES) + len(NOTE_CASES) + len(EXTRA_CASES)
    for name, payload, expect_leak in NOTE_CASES:
        text = note(payload)
        allowed = decision(payload) != "deny"
        ok = allowed and ((LEAK in text) == expect_leak)
        passed += ok
        print("  %s  %s" % ("ok  " if ok else "FAIL", name))
        if not ok:
            bad.append("%s: allowed=%s, leak note %s, want %s" % (
                name, allowed, "present" if LEAK in text else "absent",
                "present" if expect_leak else "absent"))
    print("\n%d/%d passed" % (passed, total))
    if bad:
        print("\nfailures:")
        for b in bad:
            print("  - " + b)
        return 1
    print("fail-open paths handled: exit 0 on malformed and non-dict input")
    return 0


if __name__ == "__main__":
    sys.exit(main())
