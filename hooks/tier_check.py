#!/usr/bin/env python3
"""PreToolUse hook: refuse a Workflow script whose agent() calls carry no agentType.

Since 0.5.0 it also (a) notes, never denies, an `Agent` call that names no tier and no
model — the single-call form of the same defect — and (b) warns once per session when
CLAUDE_CODE_EFFORT_LEVEL or CLAUDE_CODE_SUBAGENT_MODEL_FORCE is set, because either one
overrides every tier's pin (Claude Code docs, sub-agents, read 2026-10-22). Notes go out
as `additionalContext` as well as `systemMessage`: the docs say `systemMessage` is shown
to the user only, so before 0.5.0 the orchestrator never read them.

Why this exists as a hook and not as a paragraph
------------------------------------------------
A fan-out running entirely on the session model has been measured three times
(2026-09-30 twice, 2026-10-08 across four scripts). Two of the three got there the
way this hook catches: an agent() with no `agentType` silently inherits the
session's model — and, probed since, its effort. The third passed agentType on
every call and inherited anyway, through tiers that are `model: inherit`; the hook
notes that case and does not block it. The guidance against the first was already
written, in SKILL.md and in references/workflow-patterns.md, and was correct each
time it was ignored. Prose that has failed that often does not need another
printing; it needs an exit code. A PreToolUse `deny` is the one delivery path the
orchestrator cannot skim past.

The governing asymmetry
-----------------------
A **false deny** blocks a correct script, and the first time that happens the hook
gets switched off — after which it protects nothing. A **false allow** merely
leaves the old advisory situation in place. The two are not equally bad, so this
script is deliberately lopsided:

    when it cannot tell, it allows.

Concretely, it allows rather than denies whenever the call's parentheses do not
balance, whenever no argument is an object literal (so `agent(p, OPTS)` with
hoisted options is never blocked), whenever an object literal contains a spread
(`{...base, label}` may carry agentType through `base`), and on any unexpected
input, any exception, and any payload shape it does not recognise.

Why one scanner
---------------
An earlier version had two independent scanners — one for string/comment spans and
one for paren matching — which disagreed. A reviewer demonstrated four distinct
false denies from that split: a regex literal containing a backtick inverted code
and string regions; strings nested inside a `${}` substitution were treated as
code; and `call_end` closed a call early on a `)` inside a regex. There is now a
single pass that classifies every byte once, and everything else reads its output.
"""

import json
import os
import sys
import tempfile

HOOK_EVENT = "PreToolUse"

# Tiers whose frontmatter says `model: inherit`. Correct usage, but in a session
# running an expensive model they ARE that model — which is how the 2026-09-30
# 19-agent run cost Opus rates while passing agentType on all 18 calls.
INHERIT_TIERS = ("reviewer", "builder")

# A `/` right after one of these is a regex literal, not division.
_REGEX_OK_CHARS = set("(,=:[!&|?{};+-*/%^~<>")
_REGEX_OK_WORDS = {
    "return", "typeof", "case", "in", "of", "new", "delete", "void", "throw",
    "do", "else", "yield", "await", "instanceof",
}

STAGE_DEFAULTS = """\
  generate / draft prose or code .....  intelligent-delegate:drafter    (sonnet, high, writes)
  review / verify / audit ............  intelligent-delegate:inspector  (sonnet, medium, read-only)
  fully-specified fix from findings ..  intelligent-delegate:worker     (sonnet, medium, writes)
  convert or edit by rule and example   intelligent-delegate:mechanical (haiku, low, writes)
  the one call that gates the result .  intelligent-delegate:reviewer   (session model, high)
  contested tie-break ................  intelligent-delegate:judge      (opus, xhigh)

  Not a default, one narrow shape — pull named facts from a large input, where you can
  check the answer:                     intelligent-delegate:scout      (haiku, low, read-only)

  One stage needs more than its tier gives? Raise effort on the call before changing
  tier: {agentType: 'intelligent-delegate:inspector', effort: 'high'}."""


class Scan(object):
    """One pass over the source, classifying every byte exactly once.

    kinds[i] is the role of byte i:
        'c' code   's' string/template text   'm' comment   'r' regex literal

    `${...}` substitutions inside a template are code, and strings nested inside
    such a substitution are string again — the nesting is tracked with a stack
    rather than approximated, because approximating it was a real false-deny
    source.

    `parens` maps the index of every code-context '(' to the index just past its
    matching ')', or to None when it never closes. Callers treat None as
    "cannot tell" and allow.
    """

    def __init__(self, src):
        self.src = src
        n = len(src)
        self.kinds = ["c"] * n
        self.parens = {}
        self._scan()

    # -- helpers ---------------------------------------------------------
    def _prev_significant(self, i):
        """The last code byte before i that is not whitespace, or ''."""
        j = i - 1
        while j >= 0 and (self.kinds[j] != "c" or self.src[j] in " \t\r\n"):
            if self.kinds[j] in ("s", "m", "r"):
                # A regex may follow a comment; keep walking past it.
                j -= 1
                continue
            j -= 1
        return self.src[j] if j >= 0 else ""

    def _prev_word(self, i):
        j = i - 1
        while j >= 0 and self.src[j] in " \t\r\n":
            j -= 1
        end = j + 1
        while j >= 0 and (self.src[j].isalnum() or self.src[j] in "_$"):
            j -= 1
        return self.src[j + 1:end]

    def _regex_here(self, i):
        c = self._prev_significant(i)
        if c == "":
            return True
        if c in _REGEX_OK_CHARS:
            return True
        if c.isalnum() or c in "_$":
            return self._prev_word(i) in _REGEX_OK_WORDS
        return False

    def _mark(self, a, b, kind):
        for k in range(a, min(b, len(self.kinds))):
            self.kinds[k] = kind

    # -- the pass --------------------------------------------------------
    def _scan(self):
        src = self.src
        n = len(src)
        i = 0
        open_parens = []
        # Each entry: ('tmpl', ) for a template literal we are inside, or
        # ('sub', brace_depth) for a ${...} substitution inside one.
        stack = []

        while i < n:
            c = src[i]
            nxt = src[i + 1] if i + 1 < n else ""

            # --- comments ---
            if c == "/" and nxt == "/":
                j = src.find("\n", i)
                end = n if j == -1 else j
                self._mark(i, end, "m")
                i = end
                continue
            if c == "/" and nxt == "*":
                j = src.find("*/", i + 2)
                end = n if j == -1 else j + 2
                self._mark(i, end, "m")
                i = end
                continue

            # --- regex literal ---
            if c == "/" and self._regex_here(i):
                j = i + 1
                in_class = False
                closed = False
                while j < n:
                    d = src[j]
                    if d == "\\":
                        j += 2
                        continue
                    if d == "\n":
                        break          # unterminated: not a regex after all
                    if d == "[":
                        in_class = True
                    elif d == "]":
                        in_class = False
                    elif d == "/" and not in_class:
                        j += 1
                        closed = True
                        break
                    j += 1
                if closed:
                    while j < n and (src[j].isalpha()):
                        j += 1        # flags
                    self._mark(i, j, "r")
                    i = j
                    continue
                # Not a regex; fall through and treat '/' as code.

            # --- quoted strings ---
            if c in ("'", '"'):
                q = c
                j = i + 1
                while j < n:
                    if src[j] == "\\":
                        j += 2
                        continue
                    if src[j] == q:
                        j += 1
                        break
                    if src[j] == "\n":
                        break          # a newline ends an unterminated quote
                    j += 1
                self._mark(i, j, "s")
                i = j
                continue

            # --- template literals, with ${...} as code ---
            if c == "`":
                stack.append(("tmpl",))
                self.kinds[i] = "s"
                i += 1
                while i < n and stack and stack[-1][0] == "tmpl":
                    if src[i] == "\\":
                        self._mark(i, i + 2, "s")
                        i += 2
                        continue
                    if src[i] == "`":
                        self.kinds[i] = "s"
                        stack.pop()
                        i += 1
                        break
                    if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                        self._mark(i, i + 2, "s")
                        i += 2
                        stack.append(("sub", 1))
                        break          # resume the outer loop: this is code now
                    self.kinds[i] = "s"
                    i += 1
                continue

            # --- inside a ${...}: braces and the closing brace ---
            if stack and stack[-1][0] == "sub":
                if c == "{":
                    stack[-1] = ("sub", stack[-1][1] + 1)
                elif c == "}":
                    depth = stack[-1][1] - 1
                    if depth == 0:
                        self.kinds[i] = "s"
                        stack.pop()    # back into the enclosing template
                        i += 1
                        # Continue consuming the template text.
                        while i < n and stack and stack[-1][0] == "tmpl":
                            if src[i] == "\\":
                                self._mark(i, i + 2, "s")
                                i += 2
                                continue
                            if src[i] == "`":
                                self.kinds[i] = "s"
                                stack.pop()
                                i += 1
                                break
                            if src[i] == "$" and i + 1 < n and src[i + 1] == "{":
                                self._mark(i, i + 2, "s")
                                i += 2
                                stack.append(("sub", 1))
                                break
                            self.kinds[i] = "s"
                            i += 1
                        continue
                    stack[-1] = ("sub", depth)

            # --- paren matching, code context only ---
            if c == "(":
                open_parens.append(i)
            elif c == ")":
                if open_parens:
                    self.parens[open_parens.pop()] = i + 1
            i += 1

        for leftover in open_parens:
            self.parens[leftover] = None

    # -- queries ---------------------------------------------------------
    def code_only(self, a, b):
        """The slice a:b with every non-code byte blanked out."""
        return "".join(
            ch if self.kinds[k] == "c" else " "
            for k, ch in enumerate(self.src[a:b], start=a)
        )

    def comments(self):
        spans = []
        i, n = 0, len(self.src)
        while i < n:
            if self.kinds[i] == "m":
                j = i
                while j < n and self.kinds[j] == "m":
                    j += 1
                spans.append((i, j))
                i = j
            else:
                i += 1
        return spans


def find_agent_calls(sc):
    """Code-context `agent(` sites, as (name_start, open_paren, end_or_None)."""
    src = sc.src
    calls = []
    i = 0
    while True:
        i = src.find("agent", i)
        if i == -1:
            break
        start = i
        i += 5
        if sc.kinds[start] != "c":
            continue
        # Reject identifiers merely ending in "agent" and property accesses.
        if start > 0 and (src[start - 1].isalnum() or src[start - 1] in "_$."):
            continue
        j = start + 5
        while j < len(src) and src[j] in " \t\r\n":
            j += 1
        if j >= len(src) or src[j] != "(" or sc.kinds[j] != "c":
            continue
        calls.append((start, j, sc.parens.get(j)))
    return calls


def top_level_args(sc, open_paren, end):
    """Argument slices at depth 1 of the call, split on code-context commas."""
    src = sc.src
    inner_a, inner_b = open_paren + 1, end - 1
    args = []
    depth = 0
    seg_start = inner_a
    for k in range(inner_a, inner_b):
        if sc.kinds[k] != "c":
            continue
        ch = src[k]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            args.append((seg_start, k))
            seg_start = k + 1
    args.append((seg_start, inner_b))
    return args


def tier_of(sc, open_paren, end):
    """('tiered', value) | ('untiered', None) | ('unknown', why).

    'unknown' means allow: the script may well be correct and this check cannot
    establish otherwise.
    """
    args = top_level_args(sc, open_paren, end)
    obj = None
    for a, b in args:
        code = sc.code_only(a, b).strip()
        if code.startswith("{"):
            obj = (a, b)
    if obj is None:
        # `agent(prompt)` has no options argument at all, so nothing can be
        # hoisted into one: that is unambiguously untiered. Only a SECOND
        # argument that is not an object literal is genuinely unknown, because
        # it may be a variable holding agentType.
        # Count the arguments as WRITTEN, not as code_only renders them: a
        # string argument blanks to whitespace, so counting code made
        # `agent('x', OPTS)` look like a one-argument call and denied it.
        present = [(a, b) for a, b in args if sc.src[a:b].strip()]
        if len(present) <= 1:
            spread = any("..." in sc.code_only(a, b) for a, b in present)
            if not spread:
                return ("untiered", None)
        return ("unknown", "options passed as a variable or spread, not a literal")

    code = sc.code_only(*obj)
    if "agentType" in code:
        # Read the value: the next string literal after the key.
        key = code.index("agentType")
        tail = sc.src[obj[0] + key:obj[1]]
        value = ""
        for qi, qc in enumerate(tail):
            if qc in ("'", '"', "`"):
                closing = tail.find(qc, qi + 1)
                if closing > 0:
                    value = tail[qi + 1:closing]
                break
        return ("tiered", value)
    if "..." in code:
        return ("unknown", "object literal spreads another object")
    return ("untiered", None)


def effort_state(sc, open_paren, end):
    """'set' | 'unset' | 'unknown' — whether this call's options name an `effort`.

    Only asked of a call that has no agentType, where the answer matters: with no tier
    and no effort the agent runs at the SESSION's effort. Probed 2026-10-09 on Claude
    Code 2.1.295: `{model: 'sonnet'}` alone ran claude-sonnet-5-5 at xhigh in an xhigh
    session, and a Haiku tier that declared no effort ran at xhigh too. So a bare
    `{model: 'haiku'}` is the cheapest model at the session's thoroughness, which is
    rarely what was meant.

    'unknown' — options in a variable, or a spread that may carry it — says nothing,
    for the same reason tier_of allows what it cannot read.
    """
    args = top_level_args(sc, open_paren, end)
    obj = None
    for a, b in args:
        if sc.code_only(a, b).strip().startswith("{"):
            obj = (a, b)
    if obj is None:
        present = [(a, b) for a, b in args if sc.src[a:b].strip()]
        if len(present) <= 1 and not any("..." in sc.code_only(a, b) for a, b in present):
            return "unset"
        return "unknown"
    code = sc.code_only(*obj)
    if "..." in code:
        return "unknown"
    k = code.find("effort")
    while k != -1:
        before = code[k - 1] if k > 0 else " "
        after = code[k + 6] if k + 6 < len(code) else " "
        if not (before.isalnum() or before in "_$.") and not (after.isalnum() or after in "_$"):
            return "set"
        k = code.find("effort", k + 1)
    return "unset"


def waived(sc, start, end, comments, other_starts):
    """True if a real `// untiered: <reason>` comment waives THIS call.

    Strict, because two looser versions both leaked. A waiver must be a comment
    the scanner found — not text in a prompt string, which these very docs put
    there — it must carry a reason, and it binds to one call: if another agent()
    site sits between the comment and this one, the comment belongs to that call.
    """
    src = sc.src
    line_start = src.rfind("\n", 0, start) + 1
    probe = line_start
    for _ in range(2):
        prev = src.rfind("\n", 0, probe - 1) + 1
        if prev >= probe:
            break
        probe = prev
    nl = src.find("\n", end)
    trail_stop = len(src) if nl == -1 else nl

    for c0, c1 in comments:
        # A leading waiver must be the first thing on its line. A comment that
        # follows code is that code's trailing comment, so it belongs to the
        # call on ITS line, not to the next one down — which is how a waiver
        # written after call A silently covered call B.
        own_line_start = src.rfind("\n", 0, c0) + 1
        at_line_start = src[own_line_start:c0].strip() == ""
        leading = (probe <= c0 < line_start) and at_line_start
        trailing = end <= c0 < trail_stop
        if not (leading or trailing):
            continue
        text = src[c0:c1]
        low = text.lower()
        if "untiered:" not in low:
            continue
        reason = low.split("untiered:", 1)[1]
        reason = reason.strip(" \t*/\r\n")
        if len(reason) < 3:
            continue          # a bare marker is not a reason
        if any(c0 < o < start for o in other_starts):
            continue          # belongs to a different call
        return True
    return False


def label_of(sc, s, e):
    seg = sc.src[s:e]
    for key in ("label:", "phase:"):
        k = seg.find(key)
        if k == -1:
            continue
        rest = seg[k + len(key):].lstrip()
        if rest[:1] in ("'", '"', "`"):
            q = rest[0]
            stop = rest.find(q, 1)
            if stop > 0:
                return rest[1:stop][:60]
    return ""


# Environment variables that silently void the tier pins (Claude Code docs, sub-agents
# and model-config, read 2026-10-22). A hook inherits Claude Code's environment, so it
# can see what the orchestrator cannot.
def override_notes(session_id):
    """Notes for env vars that override every tier, once per session."""
    notes = []
    effort = os.environ.get("CLAUDE_CODE_EFFORT_LEVEL", "").strip()
    force = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE", "").strip().lower()
    forced_model = os.environ.get("CLAUDE_CODE_SUBAGENT_MODEL", "").strip()
    if effort:
        notes.append(
            "CLAUDE_CODE_EFFORT_LEVEL=%s is set: it beats both a definition's `effort:` and "
            "the call's `effort`, so every tier in this session runs at %s whatever it "
            "pins." % (effort, effort))
    if force in ("1", "true", "yes", "on") and forced_model:
        notes.append(
            "CLAUDE_CODE_SUBAGENT_MODEL_FORCE is on with CLAUDE_CODE_SUBAGENT_MODEL=%s: "
            "every subagent and workflow agent runs %s, ignoring each definition's "
            "`model:` and any `model` passed on the call — the tiers collapse onto one "
            "model." % (forced_model, forced_model))
    if not notes:
        return []
    # Say it once per session: the same paragraph on every call would only cost context.
    try:
        key = "".join(c for c in str(session_id or "nosession") if c.isalnum() or c in "-_")[:80]
        marker = os.path.join(tempfile.gettempdir(), "intelligent-delegate-override-%s" % key)
        if os.path.exists(marker):
            return []
        with open(marker, "w") as fh:
            fh.write("1")
    except Exception:
        pass
    return notes


def emit_notes(notes):
    """Allow the call, and deliver the notes to the model as well as to the user.

    `systemMessage` is shown to the user only; `additionalContext` is what reaches
    Claude (Claude Code docs, hooks). Notes meant to change the next routing decision
    are useless if only the user sees them.
    """
    text = "intelligent-delegate: " + " ".join(notes)
    print(json.dumps({
        "systemMessage": text,
        "hookSpecificOutput": {
            "hookEventName": HOOK_EVENT,
            "additionalContext": text,
        },
    }))


GENERIC_TYPES = ("", "general-purpose")


def check_agent_call(ti, session_id):
    """Note, never deny, an Agent call that names no tier and no model.

    With no `subagent_type` the call runs `general-purpose`: every tool schema
    (about 38K tokens of prefix, against 7-9K for a scoped definition), the
    session's model, and the session's effort. A one-off can be right; it should
    be a choice.
    """
    notes = override_notes(session_id)
    st = ti.get("subagent_type") or ""
    if st in GENERIC_TYPES and not ti.get("model"):
        notes.append(
            "This Agent call names no tier and no model, so it runs general-purpose on "
            "the session's model at the session's effort, with every tool schema in its "
            "prefix. Name a tier (inspector to read and judge, worker or drafter to write, "
            "scout to pull checkable facts from a large input) or pass model and effort.")
    if notes:
        emit_notes(notes)
    return 0


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(data, dict):
        return 0
    tool = data.get("tool_name")
    ti = data.get("tool_input")
    if not isinstance(ti, dict):
        return 0
    session_id = data.get("session_id")
    if tool in ("Agent", "Task"):
        return check_agent_call(ti, session_id)
    if tool != "Workflow":
        return 0
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

    sc = Scan(src)
    calls = find_agent_calls(sc)
    if not calls:
        notes = override_notes(session_id)
        if notes:
            emit_notes(notes)
        return 0
    comments = sc.comments()
    starts = [c[0] for c in calls]

    untiered, waived_n, inherit, unknown, no_effort = [], 0, 0, 0, 0
    for s, op, end in calls:
        if end is None:
            unknown += 1          # unbalanced: cannot tell, so allow
            continue
        kind, value = tier_of(sc, op, end)
        if kind == "tiered":
            if value.rsplit(":", 1)[-1] in INHERIT_TIERS:
                inherit += 1
            continue
        if kind == "unknown":
            unknown += 1
            continue
        others = [o for o in starts if o != s]
        if waived(sc, s, end, comments, others):
            waived_n += 1
            if effort_state(sc, op, end) == "unset":
                no_effort += 1
            continue
        untiered.append((src.count("\n", 0, s) + 1, label_of(sc, s, end)))

    if untiered:
        rows = "\n".join("  line %-5d %s" % (ln, lbl) for ln, lbl in untiered)
        reason = (
            "intelligent-delegate: %d of %d agent() calls in this workflow have no "
            "agentType.\n\n"
            "An agent() with no agentType is not a cheap tier — it is no tier. It "
            "inherits the session's model AND its effort, and loses the definition's "
            "maxTurns, tool allowlist, omitClaudeMd, operating rules and return-value "
            "contract. The harness logs it as agentType=\"workflow-subagent\". Measured "
            "2026-10-09 in an Opus session at xhigh: 6.2x the time and 6.6x the cost of "
            "sonnet/medium, for the same score.\n\n"
            "This is measured, not theoretical: three fan-outs ran 100%% on the session "
            "model (2026-09-30 x2, 2026-10-08). Two got there this way, with no "
            "agentType; the third passed agentType correctly and still ran Opus, "
            "because reviewer and builder are model:inherit. Fixing only this half "
            "leaves that one.\n\n"
            "%s\n\n"
            "Add agentType to each. Defaults by stage kind:\n%s\n\n"
            "Generation and verification are different jobs and should not share a "
            "tier. See intelligent-delegate's references/workflow-patterns.md, "
            "\"Per-stage tiering\".\n\n"
            "Deliberately untiered — no shipped definition has the tool surface or "
            "mandate this stage needs? Put a\n"
            "  // untiered: <reason>\n"
            "comment on or just above the call and this check passes it. Then name an "
            "effort on it: unset, it inherits the session's."
            % (len(untiered), len(calls), rows, STAGE_DEFAULTS)
        )
        extra = override_notes(session_id)
        if extra:
            reason += "\n\n" + " ".join(extra)
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": HOOK_EVENT,
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }))
        return 0

    notes = override_notes(session_id)
    if inherit:
        notes.append(
            "%d of %d agent() calls use reviewer/builder, which are `model: inherit` — "
            "in a session above Sonnet they run the session model, so they are an "
            "escalation in time and cost, to be spent where an escalation predicate "
            "fires. For ordinary review or generation, inspector (sonnet, medium) and "
            "drafter (sonnet, high) are the default: on bounded work an Opus inherit "
            "tier measured about 3x the time of inspector for the same result (a "
            "saturated task, so it says nothing about harder work). In a "
            "Sonnet session the pinned and inherit tiers run the same model." % (inherit, len(calls))
        )
    if unknown:
        notes.append(
            "%d call(s) could not be checked (options hoisted into a variable, spread, "
            "or unbalanced parentheses) and were allowed — confirm those carry an "
            "agentType." % unknown
        )
    if waived_n:
        notes.append("%d call(s) waived via `// untiered:`." % waived_n)
    if no_effort:
        notes.append(
            "%d of those set no `effort`. A call with no tier and no effort runs at the "
            "session's effort, not at a default — measured as xhigh on Haiku in an xhigh "
            "session — so it is as slow and as thorough as the session however cheap "
            "its model. Name an effort on each." % no_effort
        )
    if notes:
        emit_notes(notes)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Never let a bug here block a legitimate workflow.
        sys.exit(0)
