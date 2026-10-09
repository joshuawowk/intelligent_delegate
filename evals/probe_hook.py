#!/usr/bin/env python3
"""Run the tier-check hook end to end, in real sessions, on its four paths.

    env -u CLAUDECODE python3 evals/probe_hook.py

`hooks/test_tier_check.py` feeds the hook JSON on stdin. That proves the scanner; it
does not prove a session loads the hook, calls it before `Workflow`, or acts on what it
returns. This does: each case starts a headless `claude -p --plugin-dir <this repo>` and
asks it to run one small workflow script. Two things are then read, and neither is
anything a model said:

- **what the hook returned** — the `hook_response` event for `PreToolUse:Workflow`
  carries the hook's own stdout, so the decision and the note are parsed from that;
- **whether anything ran** — a workflow that ran leaves a subagent transcript under the
  session, and one that was refused leaves none.

    untiered agent()                 hook returns deny, and NO agent ran
    tiered                           hook returns nothing, and an agent ran
    tiered on an inherit tier        hook returns the inherit note, and an agent ran
    waived, no effort named          hook returns the unset-effort note, and an agent ran

A first version matched the deny text anywhere in the event stream, the model's own
summary included, and never checked that a refused workflow had not run.

The parent is Haiku at `low`: it only has to pass a script through, and the allowed
cases each spawn one agent that replies with a word. Bills four short sessions.
Exit status 0 only if every path behaved.
"""
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "intelligent-delegate"
DENY, INHERIT, NO_EFFORT = "have no agentType", "which are `model: inherit`", "set no `effort`"
BODY = "const r = await agent('Reply with the single word OK. Use no tools.', %s)\nreturn r"
CASES = [
    ("untiered agent()", "export const meta = {name: 'p1', description: 'probe'}\n" + BODY % "{label: 'a'}",
     {"refused": True, "says": [DENY]}),
    ("tiered", "export const meta = {name: 'p2', description: 'probe'}\n" + BODY % "{label: 'a', agentType: '%s:scout'}" % PLUGIN,
     {"refused": False, "says": []}),
    ("tiered on an inherit tier", "export const meta = {name: 'p3', description: 'probe'}\n" + BODY % "{label: 'a', agentType: '%s:reviewer'}" % PLUGIN,
     {"refused": False, "says": [INHERIT]}),
    ("waived, no effort named", "export const meta = {name: 'p4', description: 'probe'}\n// untiered: probing the waiver path\n" + BODY % "{label: 'a', model: 'haiku'}",
     {"refused": False, "says": [NO_EFFORT]}),
]


def run(script):
    prompt = ("Run a workflow for me. Call the Workflow tool exactly once, passing the text between the "
              "markers below, unchanged, as its `script` argument. Do not edit it, do not write it to a "
              "file, do not retry if it is refused. Then tell me in one line what happened.\n"
              "<<<SCRIPT\n" + script + "\nSCRIPT>>>")
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    p = subprocess.run(["claude", "-p", prompt, "--plugin-dir", REPO, "--model", "haiku", "--effort", "low",
                        "--output-format", "stream-json", "--verbose", "--include-hook-events",
                        "--permission-mode", "bypassPermissions"],
                       capture_output=True, timeout=300, env=env, cwd=REPO)
    loaded, session, hook_calls, denied, note = None, None, 0, False, ""
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") != "system":
            continue
        if r.get("subtype") == "init":
            session = r.get("session_id")
            for pl in r.get("plugins") or []:
                if isinstance(pl, dict) and pl.get("name") == PLUGIN:
                    loaded = pl.get("path")
        elif r.get("subtype") == "hook_response" and r.get("hook_name") == "PreToolUse:Workflow":
            hook_calls += 1
            try:
                out = json.loads(r.get("stdout") or r.get("output") or "{}")
            except Exception:
                out = {}
            decision = (out.get("hookSpecificOutput") or {})
            if decision.get("permissionDecision") == "deny":
                denied = True
                note += decision.get("permissionDecisionReason", "")
            note += out.get("systemMessage", "")
    ran = 0
    if session:
        ran = len(glob.glob(os.path.expanduser("~/.claude/projects/*/%s/subagents/**/agent-*.jsonl" % session),
                            recursive=True))
    return {"exit": p.returncode, "loaded": loaded, "hook_calls": hook_calls, "denied": denied,
            "note": note, "agents_ran": ran}


def judge(r, want):
    """Problems with one case. `r` is what run() observed; `want` is the case's expectation."""
    problems = []
    if r["exit"] != 0:
        problems.append("claude exited %d" % r["exit"])
    if os.path.realpath(r["loaded"] or "") != os.path.realpath(REPO):
        problems.append("plugin loaded from %s" % r["loaded"])
    if not r["hook_calls"]:
        problems.append("no PreToolUse:Workflow hook_response: the hook was never called")
    if r["denied"] != want["refused"]:
        problems.append("hook returned %s" % ("deny" if r["denied"] else "no deny"))
    if want["refused"] and r["agents_ran"]:
        problems.append("%d agent(s) ran although the call was denied" % r["agents_ran"])
    if not want["refused"] and not r["agents_ran"]:
        problems.append("no agent ran although the call was allowed")
    for marker in want["says"]:
        if marker not in r["note"]:
            problems.append("hook did not return: " + marker)
    for marker in (DENY, INHERIT, NO_EFFORT):
        if marker in r["note"] and marker not in want["says"]:
            problems.append("hook unexpectedly returned: " + marker)
    return problems


def self_test():
    ok_base = {"exit": 0, "loaded": REPO, "hook_calls": 1}
    refused, allowed = CASES[0][2], CASES[1][2]
    cases = [
        ("a clean refusal", dict(ok_base, denied=True, note=DENY, agents_ran=0), refused, True),
        ("deny returned but an agent ran anyway", dict(ok_base, denied=True, note=DENY, agents_ran=1), refused, False),
        ("no deny on an untiered call", dict(ok_base, denied=False, note="", agents_ran=1), refused, False),
        ("a clean allow", dict(ok_base, denied=False, note="", agents_ran=1), allowed, True),
        ("allowed but nothing ran", dict(ok_base, denied=False, note="", agents_ran=0), allowed, False),
        ("a tiered call denied", dict(ok_base, denied=True, note=DENY, agents_ran=0), allowed, False),
        ("the hook never called", {"exit": 0, "loaded": REPO, "hook_calls": 0, "denied": False, "note": "", "agents_ran": 1}, allowed, False),
        ("the note missing on an inherit tier", dict(ok_base, denied=False, note="", agents_ran=1), CASES[2][2], False),
        ("an unexpected note on a plain tiered call", dict(ok_base, denied=False, note=NO_EFFORT, agents_ran=1), allowed, False),
        ("the plugin loaded from another copy", dict(ok_base, loaded="/elsewhere", denied=False, note="", agents_ran=1), allowed, False),
    ]
    bad = 0
    for label, obs, want, want_ok in cases:
        ok = (not judge(obs, want)) == want_ok
        bad += not ok
        print("  %s  %-44s -> %s" % ("ok  " if ok else "FAIL", label, "passes" if want_ok else "is caught"))
    print("\n%s" % ("self-test passed" if not bad else "%d self-test case(s) FAILED" % bad))
    return 1 if bad else 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    print("checkout: %s\n" % REPO)
    bad = 0
    for name, script, want in CASES:
        try:
            r = run(script)
        except subprocess.TimeoutExpired:
            print("  FAIL  %-28s timed out" % name)
            bad += 1
            continue
        problems = judge(r, want)
        bad += bool(problems)
        outcome = ("hook returned deny; no agent ran" if want["refused"]
                   else "an agent ran; hook returned " + ("the note" if want["says"] else "nothing"))
        print("  %s  %-28s %s" % ("ok  " if not problems else "FAIL", name, outcome if not problems else "; ".join(problems)))
    print("\n%d of %d paths behaved" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
