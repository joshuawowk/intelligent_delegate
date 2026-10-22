# What the orchestrator costs

Read this when a session cost more than its subagents explain, or before a long
orchestration. `SKILL.md` → "The orchestrator is a cost centre" has the rules; this file
has the measurement, the arithmetic and the tool.

Contents
- The measurement
- Why the orchestrator dominates
- The arithmetic: re-reads, wake-ups and rebuilds
- What starts an orchestrator request
- The levers, with sources
- Measuring a session: `scripts/delegation_audit.py`

## The measurement

Two sessions, 2026-10-22, both Opus 5.5 at `xhigh` as the orchestrator, every subagent on a
pinned Sonnet tier. Figures are Claude Code's own per-model `costUSD` (cloud session
`result` events, cumulative) for the first, and `scripts/delegation_audit.py` at list prices
for the second.

| session | wall | orchestrator (Opus 5.5) | subagents (Sonnet 5.5) | orchestrator share | orchestrator context |
|---|--:|--:|--:|--:|--:|
| a 5-wave app build, `drafter` streams + reviews | ~50 min | $16.47 — 44.6M cache-read, 520K write, 195K out | $5.29 — 15.6M read, 660K write, 208K out | **76%** | ~395K per request |
| this plugin's 0.5.0 research session, 10 `worker` doc digests | 15 min | $7.24 — 15.0M read, 307K write, 90K out | $4.92 | **60%** | mean 235K, last 355K |

The subagent tiering was right in both, and in both it was the smaller term. Two sessions,
one user and one session model: read the shares as an order of magnitude, not a constant.

Cross-check: the Sonnet line of the first session — 15.63M read at $0.10, 660K 5-minute
writes at $2.50, 208K output at $10 — reproduces Claude Code's $5.29 exactly, which is how
the Sonnet 5.5 cache-read rate of $0.10 (0.05x input, not 0.1x) was confirmed against the
pricing table.

## Why the orchestrator dominates

- **Every request re-reads the whole context** at the session model's cache-read rate.
  The orchestrator's context only grows: every tool result, every subagent report, every
  hook note stays until compaction.
- **Background completions are turns.** "With nothing configured, a subagent that Claude
  spawns from your main conversation starts in the background", and "a background
  subagent's results reach Claude as a completion notification in a later turn" (Claude
  Code docs, sub-agents). Each notification is at least one full re-read; a turn that acts
  on it is several.
- **Subagents never share the orchestrator's cache.** "Its first request doesn't read the
  parent's cache, because the two prefixes differ" (Claude Code docs, prompt-caching). A
  cheap tier lowers the subagent's bill and nothing else.
- **Effort scales the orchestrator's thinking per turn.** Thinking tokens bill as output
  whether or not they are displayed, and Opus 5.5 "tends to think more per turn than Opus 5"
  at a given level (Claude Code docs, model-config).

## The arithmetic: re-reads, wake-ups and rebuilds

Cost of one request's context, before any output, at list prices (USD). A warm request
reads; a request after a cache lapse, a `/model` switch, the first fast-mode turn or a
compaction writes. Rates from the prompt-caching pricing table, read 2026-10-22.

| context | Haiku 5.5 read | Sonnet 5.5 read | Opus 5.5 read | Fable 5.1 read | Opus 5.5 5m rewrite | Opus 5.5 1h rewrite |
|--:|--:|--:|--:|--:|--:|--:|
| 100K | $0.001 | $0.01 | $0.02 | $0.025 | $0.50 | $0.80 |
| 200K | $0.01 | $0.02 | $0.04 | $0.05 | $1.00 | $1.60 |
| 400K | $0.02 | $0.04 | $0.08 | $0.10 | $2.00 | $3.20 |
| 800K | $0.04 | $0.08 | $0.16 | $0.20 | $4.00 | $6.40 |

(Haiku 5.5 bills 5x on any request whose prompt passes 100K tokens; cache tokens count.)

Worked: 40 background agents each waking a 400K Opus orchestrator for a two-request turn is
80 × $0.08 = **$6.40 of re-reads** before any thinking or output. The same 40 items as one
Workflow wake it once. If those wake-ups are more than 5 minutes apart on an API-key
session (5-minute main-loop TTL), each one rewrites instead — 40 × $2.00 = **$80**.

## What starts an orchestrator request

Each user message (one request per tool round in the turn), each background completion,
each hook that continues a turn, and idle triggers: scheduled tasks, cross-session
messages and goal check-ins (`CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0` turns those off) (Claude
Code docs, costs). Subagent and workflow requests bill on top of the main conversation's.
The `/usage` "Prompt cache (main)" line covers the main conversation only.

## The levers, with sources

1. **Workflow for fan-outs.** "A workflow script holds the loop, the branching, and the
   intermediate results itself, so Claude's context holds only the final answer" (Claude
   Code docs, workflows).
2. **Foreground when you would only wait.** A foreground `Agent` call returns as a tool
   result inside the current turn; no notification turn follows.
3. **Short reports, long output to files.** `R` is paid twice and then re-read on every
   later request until compaction.
4. **Compaction at phase boundaries, while warm.** Native-1M models auto-compact only near
   967K tokens; `/autocompact 200k` or `CLAUDE_CODE_AUTO_COMPACT_WINDOW` lowers that, and
   `/compact <focus>` does it now (Claude Code docs, model-config and context-window).
   Compacting while the cache is warm "costs a fraction of what the context size suggests";
   after a gap longer than the TTL it reprocesses everything uncached (prompt-caching). After
   compaction each invoked skill body returns capped at 5,000 tokens (25,000 total), so a
   skill's essentials belong at its top. `/btw` answers from the loaded context without
   adding the answer to history.
5. **Orchestrator effort.** Opus 5.5 defaults to `medium`; "in Anthropic's testing, Opus 5.5
   at `medium` matches or exceeds Opus 5 at `high`" (model-config). On Opus 5.5, Sonnet 5.5,
   Haiku 5.5 and Fable 5.1 with an API key or subscription, "changing effort keeps the
   cache" (prompt-caching) — not on Bedrock, Google Cloud's Agent Platform, a Claude apps
   gateway, HIPAA, or with `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS`. Not measured here.
6. **Cache lifetime.** The main loop gets a 1-hour TTL only on a subscription within plan
   usage; API keys, cloud providers and usage credits get 5 minutes. `promptCacheTtl` /
   `CLAUDE_CODE_PROMPT_CACHE_TTL` set the main loop's; `subagentPromptCacheTtl` /
   `CLAUDE_CODE_SUBAGENT_PROMPT_CACHE_TTL` and frontmatter `experimental.cacheTtl` set
   subagents' (v2.1.242+; prompt-caching).
7. **No mid-orchestration `/model` switch.** It rebuilds the cache, and it moves every
   `inherit` tier with it.
8. **Not measured, documented:** a nested coordinator — a subagent whose `tools` include
   `Agent` — waits for its own children, so only its summary returns (sub-agents; depth
   `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, default 3). Agent view sessions report to the
   user, not to an orchestrator.

## Measuring a session: `scripts/delegation_audit.py`

```
python3 <plugin root>/scripts/delegation_audit.py               # newest transcript
python3 <plugin root>/scripts/delegation_audit.py <session-id>
python3 <plugin root>/scripts/delegation_audit.py path/to/session.jsonl --json
```

It reads `~/.claude/projects/<cwd-slug>/<session-id>.jsonl` and the
`<session-id>/subagents/agent-*.jsonl` transcripts beside it, counts usage once per API
response (`message.id`; a response is logged once per content block), and prints spend by
model, the orchestrator's share, mean and last prompt size, background notifications, cache
rebuilds, and each subagent's tier, model, effort, requests, wall time and cost.

Findings and their thresholds (each a judgement, stated so it can be argued with):

| code | fires when | rule it points at |
|---|---|---|
| `orchestrator-heavy` | subagents ran and the orchestrator is over 50% of spend | levers 1-5 |
| `large-orchestrator-context` | mean orchestrator prompt over 150K tokens | lever 4 |
| `notification-wakeups` | any background completion reached the orchestrator | lever 1-2 |
| `cache-rebuilds` | a later request wrote more than half of a 20K+ prompt | levers 6-7 |
| `untiered-subagents` | a subagent ran as `general-purpose`, `workflow-subagent` or unknown | anti-pattern 10, 16 |
| `session-model-fanout` | 3+ subagents ran on the session model | anti-pattern 14 |
| `inherited-effort` | a non-inherit subagent ran at the session's `xhigh`/`max` | anti-pattern 16 |
| `advisor-above-tier` | an attached advisor's model is pricier than the subagent's | the advisor bullet |

Limits: costs are list-price estimates (no batch, fast mode, data residency); advisor
consults run server-side and are not itemised separately; a cloud session's `result`
events carry Claude Code's own cumulative per-model `costUSD`, which is authoritative where
the orchestrator and its tiers run different models. Tests: `scripts/test_delegation_audit.py`.
