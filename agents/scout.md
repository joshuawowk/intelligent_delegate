---
name: scout
description: "Cheapest reading tier (Haiku, low effort, read-only). Use to pull named facts out of a large input — counting or locating entries in a long log, extracting fields from a changelog, finding which of many files mention something — when the answer is one you can check, or a wrong one is cheap. Cheap, not fast, and not exact: on a ten-question log extraction it measured a thirteenth of `inspector`'s cost at about the same speed, and got 48 of 50 answers right where every Sonnet and Opus run got them all. Both misses were one shape — reading the line next to a match. Reach for it in a fan-out or over a very large corpus. For one read you will act on unchecked, use `inspector`. Do NOT use for review, audit, an absence proof or any verdict, and not for work that edits files."
model: haiku
effort: low
maxTurns: 25
omitClaudeMd: true
tools:
  - Read
  - Grep
  - Glob
  - Bash
---

# Scout tier

(body to be written from docs/design-0.4.0.md, section 7)
