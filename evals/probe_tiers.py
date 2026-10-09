#!/usr/bin/env python3
"""Spawn every tier once in a fresh session and check what it actually ran as.

    env -u CLAUDECODE python3 evals/probe_tiers.py            # all tiers
    env -u CLAUDECODE python3 evals/probe_tiers.py scout judge

For each `agents/*.md` this starts a headless `claude -p --plugin-dir <this repo>`,
has it spawn that one tier on a one-line task, then reads the SUBAGENT's transcript
for the `requestedModel` and `effort` the harness recorded — not anything the model
said about itself — and compares them with the definition's frontmatter.

The parent session runs Haiku at `max`. Both choices are there to make a wrong
result visible rather than to save money:

- `max` is an effort no tier pins, so a tier that failed to carry its own effort
  would show `max` instead of quietly matching the session. (This is how 0.3.0's
  `mechanical` was caught: it declared no effort and ran at the session's.)
- Haiku is a model only the Haiku tiers pin, so an `inherit` tier that resolves
  anywhere but the session shows up, and a pinned tier that fell back to
  inheriting shows up too.

It also confirms, from the session's own init event, that the plugin was loaded
from this checkout. A probe of some other installed copy would pass or fail for
reasons that have nothing to do with these files.

Bills one short `claude -p` session per tier. Exit status 0 only if every tier matched.
"""
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "intelligent-delegate"
SESSION_MODEL, SESSION_EFFORT = "haiku", "max"
ALIAS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5",
         "fable": "claude-fable-5-1"}


def frontmatter(path):
    text = open(path).read()
    block = text.split("\n---\n", 1)[0].split("---\n", 1)[1]
    out = {}
    for line in block.split("\n"):
        if line and not line.startswith((" ", "-")) and ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def probe(name):
    prompt = ("Call the Agent tool exactly once, with subagent_type '%s:%s' and the prompt "
              "'Reply with the single word PROBE and nothing else. Use no tools.' "
              "Do not pass a model or an effort. When it returns, reply DONE." % (PLUGIN, name))
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        p = subprocess.run(["claude", "-p", prompt, "--plugin-dir", REPO, "--model", SESSION_MODEL,
                            "--effort", SESSION_EFFORT, "--output-format", "stream-json", "--verbose"],
                           capture_output=True, timeout=300, env=env, cwd=REPO)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    if p.returncode != 0:
        return {"error": "claude exited %d: %s" % (p.returncode, p.stderr.decode("utf-8", "replace")[-200:])}
    session, loaded, session_model = None, None, None
    for line in p.stdout.decode("utf-8", "replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and r.get("type") == "system" and r.get("subtype") == "init":
            session, session_model = r.get("session_id"), r.get("model")
            for pl in r.get("plugins") or []:
                if isinstance(pl, dict) and pl.get("name") == PLUGIN:
                    loaded = pl.get("path")
    if not session:
        return {"error": "no init event in the output"}
    pattern = os.path.expanduser("~/.claude/projects/*/%s/subagents/agent-*.jsonl" % session)
    models, efforts, kinds = set(), set(), set()
    for path in glob.glob(pattern):
        meta = path.replace(".jsonl", ".meta.json")
        if os.path.exists(meta):
            kinds.add(json.load(open(meta)).get("agentType"))
        for line in open(path, errors="replace"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("type") == "assistant":
                if r.get("requestedModel"):
                    models.add(r["requestedModel"])
                if r.get("effort"):
                    efforts.add(r["effort"])
    return {"loaded": loaded, "session_model": session_model, "agent_types": sorted(k for k in kinds if k),
            "models": sorted(models), "efforts": sorted(efforts), "error": None}


def main(argv):
    names = argv[1:] or sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(REPO, "agents", "*.md")))
    print("checkout            : %s" % REPO)
    print("parent session      : %s at effort %s (an effort no tier pins, so inheritance cannot hide)" % (SESSION_MODEL, SESSION_EFFORT))
    print()
    print("%-11s %-22s %-22s %-10s %-10s %s" % ("tier", "declares", "ran as", "declares", "ran at", ""))
    bad = 0
    for name in names:
        fm = frontmatter(os.path.join(REPO, "agents", name + ".md"))
        r = probe(name)
        if r.get("error"):
            print("%-11s ERROR %s" % (name, r["error"]))
            bad += 1
            continue
        want_model = ALIAS[SESSION_MODEL] if fm["model"] == "inherit" else ALIAS.get(fm["model"], fm["model"])
        want_effort = fm.get("effort", SESSION_EFFORT)
        problems = []
        if os.path.realpath(r["loaded"] or "") != os.path.realpath(REPO):
            problems.append("plugin loaded from %s" % r["loaded"])
        if r["agent_types"] != ["%s:%s" % (PLUGIN, name)]:
            problems.append("spawned %s" % (r["agent_types"] or "nothing"))
        if r["models"] != [want_model]:
            problems.append("model")
        if r["efforts"] != [want_effort]:
            problems.append("effort")
        bad += bool(problems)
        print("%-11s %-22s %-22s %-10s %-10s %s" % (
            name, fm["model"] + (" -> " + want_model if fm["model"] == "inherit" else ""),
            ",".join(r["models"]) or "-", fm.get("effort", "(none)"), ",".join(r["efforts"]) or "-",
            "ok" if not problems else "MISMATCH: " + "; ".join(problems)))
    print()
    print("%d of %d tiers ran as declared" % (len(names) - bad, len(names)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
