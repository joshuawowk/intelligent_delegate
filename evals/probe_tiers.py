#!/usr/bin/env python3
"""Spawn every tier once in a fresh session and check what it actually ran as.

    env -u CLAUDECODE python3 evals/probe_tiers.py            # all tiers
    env -u CLAUDECODE python3 evals/probe_tiers.py scout judge
    python3 evals/probe_tiers.py --self-test                  # the comparison logic only; bills nothing

For each `agents/*.md` this starts a headless `claude -p --plugin-dir <this repo>`,
has it spawn that one tier on a one-line task, then reads the SUBAGENT's transcript
for the `requestedModel` and `effort` the harness recorded — not anything the model
said about itself — and compares them with the definition's frontmatter.

The parent session is chosen so that a tier which had lost a pin could not pass by
inheriting the same value:

- **Effort.** The parent runs at `max`, which no tier pins. A tier that declares no
  `effort:` is a MISMATCH outright — it would run at the session's, which is the
  0.3.0 defect in `mechanical` this script exists to catch. (A first version of this
  script expected the session's effort in that case, observed it, and printed `ok`.)
- **Model.** The parent's model is one the tier does NOT pin: Sonnet for the Haiku
  tiers, Haiku for everything else. So a `model: haiku` that stopped being honoured
  would show Sonnet, and an `inherit` tier is expected to show the parent's.

It also confirms, from the session's own init event, that the plugin was loaded from
this checkout and that the parent ran the model it was asked to.

Bills one short `claude -p` session per tier. Exit status 0 only if every tier matched.
"""
import glob
import json
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "intelligent-delegate"
SESSION_EFFORT = "max"
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


def parent_for(fm):
    """A parent model this tier does not pin, so a lost pin cannot pass by inheritance."""
    return "sonnet" if fm.get("model") == "haiku" else "haiku"


def judge(name, fm, seen, parent):
    """Problems with one probe, as a list of strings. Empty means the tier ran as declared.

    `seen` is {loaded, session_model, agent_types, models, efforts}; `parent` is the alias
    the parent session was started on.
    """
    problems = []
    if os.path.realpath(seen.get("loaded") or "") != os.path.realpath(REPO):
        problems.append("plugin loaded from %s" % seen.get("loaded"))
    if ALIAS[parent] not in (seen.get("session_model") or ""):
        problems.append("parent ran %s, not %s" % (seen.get("session_model"), ALIAS[parent]))
    if seen.get("agent_types") != ["%s:%s" % (PLUGIN, name)]:
        problems.append("spawned %s" % (seen.get("agent_types") or "nothing"))
    declared = fm.get("model")
    if not declared:
        problems.append("declares no model")
    else:
        want_model = ALIAS[parent] if declared == "inherit" else ALIAS.get(declared, declared)
        if seen.get("models") != [want_model]:
            problems.append("model: ran %s, wanted %s" % (seen.get("models"), want_model))
    if "effort" not in fm:
        problems.append("declares no effort, so it runs at the session's")
    elif seen.get("efforts") != [fm["effort"]]:
        problems.append("effort: ran %s, wanted %s" % (seen.get("efforts"), fm["effort"]))
    return problems


def probe(name, parent):
    prompt = ("Call the Agent tool exactly once, with subagent_type '%s:%s' and the prompt "
              "'Reply with the single word PROBE and nothing else. Use no tools.' "
              "Do not pass a model or an effort. When it returns, reply DONE." % (PLUGIN, name))
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        p = subprocess.run(["claude", "-p", prompt, "--plugin-dir", REPO, "--model", parent,
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


def self_test():
    """The comparison, on synthetic observations. A probe that cannot fail proves nothing."""
    def seen(model, effort, name="t", parent="haiku"):
        return {"loaded": REPO, "session_model": ALIAS[parent], "agent_types": ["%s:%s" % (PLUGIN, name)],
                "models": [ALIAS[model]], "efforts": [effort]}
    cases = [
        ("a pinned tier that ran as declared", {"model": "sonnet", "effort": "medium"}, seen("sonnet", "medium"), "haiku", True),
        ("NO effort declared, and it ran at the session's", {"model": "haiku"}, seen("haiku", "max", parent="sonnet"), "sonnet", False),
        ("effort declared but not honoured", {"model": "sonnet", "effort": "medium"}, seen("sonnet", "max"), "haiku", False),
        ("a Haiku pin lost: it inherited the Sonnet parent", {"model": "haiku", "effort": "low"}, seen("sonnet", "low", parent="sonnet"), "sonnet", False),
        ("a Sonnet pin lost: it inherited the Haiku parent", {"model": "sonnet", "effort": "high"}, seen("haiku", "high"), "haiku", False),
        ("inherit resolving to the parent", {"model": "inherit", "effort": "high"}, seen("haiku", "high"), "haiku", True),
        ("inherit resolving somewhere else", {"model": "inherit", "effort": "high"}, seen("opus", "high"), "haiku", False),
        ("the plugin loaded from another copy", {"model": "sonnet", "effort": "medium"},
         dict(seen("sonnet", "medium"), loaded="/elsewhere"), "haiku", False),
        ("the wrong agent type spawned", {"model": "sonnet", "effort": "medium"},
         dict(seen("sonnet", "medium"), agent_types=["general-purpose"]), "haiku", False),
        ("the parent did not run the model asked for", {"model": "haiku", "effort": "low"},
         dict(seen("haiku", "low", parent="sonnet"), session_model=ALIAS["haiku"]), "sonnet", False),
    ]
    bad = 0
    for label, fm, obs, parent, want_ok in cases:
        ok = (not judge("t", fm, obs, parent)) == want_ok
        bad += not ok
        print("  %s  %-52s -> %s" % ("ok  " if ok else "FAIL", label, "passes" if want_ok else "is caught"))
    for model in ("haiku", "sonnet", "opus", "inherit"):
        ok = model == "inherit" or parent_for({"model": model}) != model
        bad += not ok
        print("  %s  the parent chosen for a `%s` tier is not %s" % ("ok  " if ok else "FAIL", model, "its own pin" if model != "inherit" else "(it inherits by design)"))
    print("\n%s" % ("self-test passed" if not bad else "%d self-test case(s) FAILED" % bad))
    return 1 if bad else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    names = argv[1:] or sorted(os.path.basename(f)[:-3] for f in glob.glob(os.path.join(REPO, "agents", "*.md")))
    print("checkout : %s" % REPO)
    print("parents  : effort %s (no tier pins it); model sonnet for the Haiku tiers, haiku for the rest\n" % SESSION_EFFORT)
    print("%-11s %-8s %-20s %-20s %-9s %-8s %s" % ("tier", "parent", "declares", "ran as", "declares", "ran at", ""))
    bad = 0
    for name in names:
        fm = frontmatter(os.path.join(REPO, "agents", name + ".md"))
        parent = parent_for(fm)
        r = probe(name, parent)
        if r.get("error"):
            print("%-11s %-8s ERROR %s" % (name, parent, r["error"]))
            bad += 1
            continue
        problems = judge(name, fm, r, parent)
        bad += bool(problems)
        print("%-11s %-8s %-20s %-20s %-9s %-8s %s" % (
            name, parent, fm.get("model", "(none)") + (" -> parent's" if fm.get("model") == "inherit" else ""),
            ",".join(r["models"]) or "-", fm.get("effort", "(none)"), ",".join(r["efforts"]) or "-",
            "ok" if not problems else "MISMATCH: " + "; ".join(problems)))
    print("\n%d of %d tiers ran as declared" % (len(names) - bad, len(names)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
