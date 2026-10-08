#!/usr/bin/env python3
"""PreToolUse hook: refuse a Workflow script whose agent() calls carry no agentType.

Why this exists as a hook and not as a paragraph
------------------------------------------------
The same defect has now been measured three times (2026-09-30 twice, 2026-10-08
across four scripts): every agent() call in a fan-out ran on the session model,
because an agent() with no `agentType` silently inherits it. The guidance against
this was already written — in SKILL.md and in 300 lines of
references/workflow-patterns.md — and was correct both times it was ignored.

Prose that has failed three times does not need a fourth printing. It needs an
exit code. A PreToolUse hook is the only delivery path the orchestrator cannot
skim past: `permissionDecision: deny` blocks the call and the reason is fed back
as the next thing the model reads.

Design constraints this script holds itself to
----------------------------------------------
* **Fail open, always.** Any internal error, any unparseable input, any shape it
  does not recognise exits 0 and allows the call. A cost-control hook that
  wedges a legitimate workflow would be turned off within a day, and then it
  protects nothing. Blocking is reserved for the case it is certain about.
* **No false positives from prompt text.** Workflow prompts routinely discuss
  `agent()` — this plugin's own docs do. A regex over the raw source would flag
  those and block a correct script. So the script lexes: string bodies,
  template-literal bodies and comments are not code, and `agent(` inside them is
  never a call site.
* **One escape hatch, deliberately narrow.** `{effort: 'max'}` is unreachable
  from frontmatter, so bare opts are sometimes right. A `// untiered: <reason>`
  comment on or just above the call passes it. Requiring a *reason* is the
  point: it costs a sentence of thought, which is all the check is trying to buy.
* **Deny only what is unambiguous.** A missing agentType is always a defect.
  Choosing `reviewer`/`builder` is a legitimate escalation, so that is a
  non-blocking note, not a block.
"""

import json
import sys

HOOK_EVENT = "PreToolUse"

# Tiers whose frontmatter says `model: inherit`. Correct usage, but in a session
# running an expensive model they are that model — which is exactly how the
# 2026-09-30 run cost Opus rates while passing agentType on all 18 calls.
INHERIT_TIERS = ("reviewer", "builder")

STAGE_DEFAULTS = """\
  generate / draft prose or code .....  intelligent-delegate:drafter    (sonnet, high, writes)
  review / verify / audit ............  intelligent-delegate:inspector  (sonnet, high, read-only)
  fully-specified fix from findings ..  intelligent-delegate:worker     (sonnet, medium, writes)
  mechanical transcription ...........  intelligent-delegate:mechanical (haiku, no effort)
  the one call that gates the result .  intelligent-delegate:reviewer   (session model, high)
  contested tie-break ................  intelligent-delegate:judge      (opus, xhigh)"""


def lex_code_spans(src):
    """Yield (start, end) index pairs covering the parts of `src` that are code.

    Everything else — single/double-quoted strings, template-literal text,
    line and block comments — is excluded. Template `${...}` substitutions ARE
    code and are included, because an agent() call can legitimately appear
    inside one.

    Deliberately not a full JS parser. The one construct it knowingly does not
    disambiguate is a regex literal containing a quote or a slash-star; such a
    regex could desynchronise the scan. That failure direction is safe: a
    desynchronised scan finds fewer call sites, so the hook under-reports and
    allows, never over-reports and blocks.
    """
    spans = []
    i, n = 0, len(src)
    code_start = 0
    # Stack of template-literal depths we are inside, so nested `${`/`}` pair up.
    tmpl_stack = []
    brace_stack = []

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""

        if c == "/" and nxt == "/":
            spans.append((code_start, i))
            j = src.find("\n", i)
            i = n if j == -1 else j
            code_start = i
            continue

        if c == "/" and nxt == "*":
            spans.append((code_start, i))
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            code_start = i
            continue

        if c in ("'", '"'):
            spans.append((code_start, i))
            q = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                # An unterminated quote would run to EOF; a newline ends it
                # instead, which keeps a stray apostrophe in a comment-like
                # position from swallowing the rest of the file.
                if src[i] == "\n":
                    break
                i += 1
            code_start = i
            continue

        if c == "`":
            spans.append((code_start, i))
            i += 1
            tmpl_stack.append(True)
            # Walk the literal, re-entering code for each ${ ... }.
            while i < n and tmpl_stack:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "`":
                    i += 1
                    tmpl_stack.pop()
                    break
                if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                    i += 2
                    sub_start = i
                    depth = 1
                    while i < n and depth:
                        ch = src[i]
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                break
                        elif ch in ("'", '"', "`"):
                            # Nested string inside the substitution: skip it so a
                            # brace in its text cannot unbalance the depth count.
                            q = ch
                            i += 1
                            while i < n:
                                if src[i] == "\\":
                                    i += 2
                                    continue
                                if src[i] == q:
                                    break
                                i += 1
                        i += 1
                    spans.append((sub_start, min(i, n)))
                    i += 1
                    continue
                i += 1
            code_start = i
            continue

        i += 1

    spans.append((code_start, n))
    return [(a, b) for a, b in spans if b > a]


def in_spans(idx, spans):
    for a, b in spans:
        if a <= idx < b:
            return True
    return False


def call_end(src, open_paren):
    """Index just past the ) that closes the ( at `open_paren`.

    Skips over strings, template literals and comments so a paren inside prompt
    text cannot close the call early.
    """
    i, n = open_paren, len(src)
    depth = 0
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c in ("'", '"', "`"):
            q = c
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == q:
                    i += 1
                    break
                i += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def find_agent_calls(src, spans):
    """Locate `agent(` call sites that are real code, not prompt text."""
    calls = []
    i = 0
    while True:
        i = src.find("agent", i)
        if i == -1:
            break
        start = i
        i += 5
        if not in_spans(start, spans):
            continue
        # Reject identifiers that merely end in "agent" (subagent, myAgent) and
        # property accesses (foo.agent).
        if start > 0 and (src[start - 1].isalnum() or src[start - 1] in "_$."):
            continue
        j = start + 5
        while j < len(src) and src[j] in " \t\n":
            j += 1
        if j >= len(src) or src[j] != "(":
            continue
        calls.append((start, j, call_end(src, j)))
    return calls


def has_untiered_waiver(src, start):
    """True if a `// untiered: <reason>` comment sits on or just above the call."""
    line_start = src.rfind("\n", 0, start) + 1
    # The call's own line, plus the two above it — enough for a comment placed
    # over a call that begins on its own line in a pipeline stage.
    probe_start = line_start
    for _ in range(2):
        prev = src.rfind("\n", 0, probe_start - 1) + 1
        if prev >= probe_start:
            break
        probe_start = prev
    # Extend to the end of the line the call ENDS on, so a trailing
    # `) // untiered: ...` is inside the window too.
    end = call_end(src, start)
    nl = src.find("\n", end)
    window = src[probe_start:(len(src) if nl == -1 else nl)]
    low = window.lower()
    return "untiered:" in low and ("//" in window or "/*" in window)


def label_of(src, s, e):
    """Best-effort stage label, so the report points at a recognisable call."""
    seg = src[s:e]
    for key in ("label:", "phase:"):
        k = seg.find(key)
        if k == -1:
            continue
        rest = seg[k + len(key):].lstrip()
        if rest[:1] in ("'", '"', "`"):
            q = rest[0]
            end = rest.find(q, 1)
            if end > 0:
                return rest[1:end][:60]
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    if data.get("tool_name") != "Workflow":
        return 0

    ti = data.get("tool_input") or {}
    src = ti.get("script")
    if not src:
        path = ti.get("scriptPath")
        if path:
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    src = fh.read()
            except Exception:
                return 0
    # A saved workflow invoked by `name` has no script here to inspect.
    if not src or not isinstance(src, str):
        return 0

    spans = lex_code_spans(src)
    calls = find_agent_calls(src, spans)
    if not calls:
        return 0

    untiered, waived, inherit = [], 0, 0
    for s, op, e in calls:
        seg = src[s:e]
        if "agentType" in seg:
            if any(("%s" % t) in seg for t in INHERIT_TIERS):
                inherit += 1
            continue
        if has_untiered_waiver(src, s):
            waived += 1
            continue
        untiered.append((src.count("\n", 0, s) + 1, label_of(src, s, e)))

    if untiered:
        rows = "\n".join(
            "  line %-5d %s" % (ln, lbl) for ln, lbl in untiered
        )
        reason = (
            "intelligent-delegate: %d of %d agent() calls in this workflow have no "
            "agentType.\n\n"
            "An agent() with no agentType is not a cheap tier — it is no tier. It "
            "inherits the session model and loses the definition's maxTurns, tool "
            "allowlist, omitClaudeMd, operating rules and return-value contract. The "
            "harness logs it as agentType=\"workflow-subagent\".\n\n"
            "This is measured, not theoretical: three fan-outs (2026-09-30 x2, "
            "2026-10-08 x4 scripts) ran 100%% on the session model this way, at roughly "
            "2.5x the Sonnet cost for the same tokens.\n\n"
            "%s\n\n"
            "Add agentType to each. Defaults by stage kind:\n%s\n\n"
            "Generation and verification are different jobs and should not share a "
            "tier. See intelligent-delegate's references/workflow-patterns.md, "
            "\"Per-stage tiering\".\n\n"
            "Deliberately untiered — you need effort:'max', or bare {model, effort} "
            "that no definition expresses? Put a\n"
            "  // untiered: <reason>\n"
            "comment on or just above the call and this check passes it."
            % (len(untiered), len(calls), rows, STAGE_DEFAULTS)
        )
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
        return 0

    if inherit:
        note = (
            "intelligent-delegate: every agent() carries an agentType — good. Note "
            "that %d of %d use reviewer/builder, which are `model: inherit`: in this "
            "session they run the session model, so they are an escalation, not a "
            "saving. If the stage is ordinary review or ordinary generation, "
            "inspector/drafter (sonnet, high) do it at roughly half the cost."
            % (inherit, len(calls))
        )
        if waived:
            note += " %d call(s) waived via `// untiered:`." % waived
        print(json.dumps({"systemMessage": note}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never let a bug here block a legitimate workflow.
        sys.exit(0)
