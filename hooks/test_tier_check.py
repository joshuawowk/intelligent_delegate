#!/usr/bin/env python3
"""Tests for the tier-check hook. Run: python3 hooks/test_tier_check.py

Every case below is here because it is a way the hook could be wrong in a
direction that matters. The expensive-wrong direction is a false DENY on a
correct script — that gets the hook disabled — so most of these are allow cases.
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
    if not out:
        return None
    return json.loads(out)


def decision(payload):
    d = run(payload)
    if not d:
        return "allow"
    h = d.get("hookSpecificOutput")
    if h:
        return h.get("permissionDecision")
    return "allow+note"


def wf(script):
    return {"tool_name": "Workflow", "tool_input": {"script": script}}


CASES = []


def case(name, payload, expect):
    CASES.append((name, payload, expect))


# --- the defect it exists to catch -----------------------------------------
case("bare agent() is denied", wf("""
export const meta = {name:'x', description:'y'}
const r = await agent('do a thing', {label:'a', phase:'P'})
"""), "deny")

case("one tiered + one bare is still denied", wf("""
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
const b = await agent('y', {label:'b'})
"""), "deny")

# --- correct scripts must pass ---------------------------------------------
case("fully tiered passes clean", wf("""
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:drafter'})
const b = await agent('y', {label:'b', agentType:'intelligent-delegate:inspector'})
"""), "allow")

case("inherit tier passes with a note", wf("""
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:reviewer'})
"""), "allow+note")

case("no agent() at all passes", wf("""
export const meta = {name:'x', description:'y'}
return {ok: true}
"""), "allow")

# --- the escape hatch ------------------------------------------------------
case("waiver on the line above passes", wf("""
// untiered: needs effort 'max', which frontmatter cannot express
const a = await agent('x', {label:'a', effort:'max'})
"""), "allow+note" if False else "allow")

case("waiver on the same line passes", wf("""
const a = await agent('x', {label:'a', effort:'max'}) // untiered: max effort
"""), "allow")

case("a waiver without the word untiered does NOT pass", wf("""
// this one is fine honestly, trust me
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

case("a ${} substitution inside a template IS code", wf("""
const out = `${await agent('x', {label:'a'})}`
"""), "deny")

case("parens inside the prompt do not end the call early", wf("""
const a = await agent('see foo(bar) and baz(qux) for context',
  {label:'a', agentType:'intelligent-delegate:inspector'})
"""), "allow")

case("apostrophe in a comment does not desync the scan", wf("""
// this doesn't break the lexer
const a = await agent('x', {label:'a', agentType:'intelligent-delegate:worker'})
"""), "allow")

# --- fail-open behaviour ---------------------------------------------------
case("a non-Workflow tool is ignored", {"tool_name": "Bash",
     "tool_input": {"command": "agent('x', {})"}}, "allow")
case("a saved workflow invoked by name is ignored",
     {"tool_name": "Workflow", "tool_input": {"name": "review-changes"}}, "allow")
case("missing tool_input is ignored", {"tool_name": "Workflow"}, "allow")
case("a non-string script is ignored",
     {"tool_name": "Workflow", "tool_input": {"script": 42}}, "allow")


def main():
    # Garbage on stdin must still exit 0 and allow.
    p = subprocess.run([sys.executable, HOOK], input="not json at all",
                       capture_output=True, text=True, timeout=30)
    bad = []
    if p.returncode != 0:
        bad.append("malformed stdin: exit %d, want 0" % p.returncode)

    passed = 0
    for name, payload, expect in CASES:
        got = decision(payload)
        if got == expect:
            passed += 1
            print("  ok    %s" % name)
        else:
            bad.append("%s: got %s, want %s" % (name, got, expect))
            print("  FAIL  %s -> %s (want %s)" % (name, got, expect))

    print("\n%d/%d passed" % (passed, len(CASES)))
    if bad:
        print("\nfailures:")
        for b in bad:
            print("  - " + b)
        return 1
    print("malformed stdin handled: exit 0")
    return 0


if __name__ == "__main__":
    sys.exit(main())
