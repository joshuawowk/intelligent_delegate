---
name: audit
description: "Audits where this session's spend and time went — the orchestrator's own context against each subagent's tier, model, effort and cost — and flags the patterns behind an expensive session: an orchestrator-heavy split, a large re-read context, background-completion wake-ups, cache rebuilds, untiered or session-model subagents, inherited effort, and an advisor priced above the tier. Invoke with /intelligent-delegate:audit, optionally followed by a session id or a transcript path."
disable-model-invocation: true
license: MIT
---

# Audit this session's delegation spend

Run the bundled script with Bash. It lives at `scripts/delegation_audit.py` in this
plugin's root, two directories above this skill's base directory:

```
python3 "<this skill's base directory>/../../scripts/delegation_audit.py" $ARGUMENTS
```

With no argument it audits the most recently modified transcript under
`~/.claude/projects`, which is this session's. With an argument it takes a session id or
a transcript path. Add `--json` for machine-readable output.

Then report to the user, in this order and briefly:

1. The split: estimated total, orchestrator share, and the top three subagents by cost.
2. Each finding the script printed, with the one action that addresses it. The actions
   are in `skills/delegate/references/orchestrator-cost.md` → "The levers, with sources";
   only the user can run `/compact`, `/clear`, `/effort`, `/model` and `/advisor`, so name
   the command for them rather than implying you ran it.
3. One line on the limits: costs are list-price estimates from the transcript; advisor
   consults are not itemised.

Do not paste the full table unless the user asks for it.
