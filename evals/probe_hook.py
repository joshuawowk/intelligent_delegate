#!/usr/bin/env python3
"""Run the tier-check hook end to end, in real sessions, on its four paths.

    env -u CLAUDECODE python3 evals/probe_hook.py

`hooks/test_tier_check.py` feeds the hook JSON on stdin. That proves the scanner; it
does not prove a session loads the hook, calls it before `Workflow`, or surfaces what
it says. This does: each case starts a headless `claude -p --plugin-dir <this repo>`,
asks it to run one small workflow script, and reads the session's own event stream.

    untiered agent()                 the call must be refused, with the deny reason
    tiered                           must run, and the hook must say nothing
    tiered on an inherit tier        must run, with the inherit note
    waived, no effort named          must run, with the unset-effort note

The parent is Haiku at `low`: it only has to pass a script through, and the allowed
cases each spawn one agent that replies with a word. Bills four short sessions.
Exit status 0 only if every path behaved.
"""
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
    loaded, called, said = None, 0, set()
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("type") == "system" and r.get("subtype") == "init":
            for pl in r.get("plugins") or []:
                if isinstance(pl, dict) and pl.get("name") == PLUGIN:
                    loaded = pl.get("path")
        blob = json.dumps(r)
        if '"tool_use"' in blob and '"name": "Workflow"' in blob:
            called += 1
        for marker in (DENY, INHERIT, NO_EFFORT):
            if marker in blob and (PLUGIN + ":") in blob:
                said.add(marker)
    return {"exit": p.returncode, "loaded": loaded, "called": called, "said": said}


def main():
    print("checkout: %s\n" % REPO)
    bad = 0
    for name, script, want in CASES:
        try:
            r = run(script)
        except subprocess.TimeoutExpired:
            print("  FAIL  %-28s timed out" % name)
            bad += 1
            continue
        problems = []
        if os.path.realpath(r["loaded"] or "") != os.path.realpath(REPO):
            problems.append("plugin loaded from %s" % r["loaded"])
        if not r["called"]:
            problems.append("the session never called Workflow, so the hook was not exercised")
        if (DENY in r["said"]) != want["refused"]:
            problems.append("refused" if DENY in r["said"] else "not refused")
        for marker in want["says"]:
            if marker not in r["said"]:
                problems.append("did not say: " + marker)
        for marker in r["said"] - set(want["says"]):
            problems.append("unexpectedly said: " + marker)
        bad += bool(problems)
        outcome = "refused" if want["refused"] else "ran" + (", note surfaced" if want["says"] else ", hook silent")
        print("  %s  %-28s %s" % ("ok  " if not problems else "FAIL", name, outcome if not problems else "; ".join(problems)))
    print("\n%d of %d paths behaved" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
