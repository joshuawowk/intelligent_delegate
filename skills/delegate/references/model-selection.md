# Model and effort selection

Read this when a tier call is genuinely close — the skill body handles the easy
cases; this file prices the hard ones.

## Cost table

First-party API rates, USD per million tokens. Cross-checked 2026-10-01 against the model
catalog in Claude Code 2.1.286 (`tier_2_10`, `tier_5_25`, `tier_4_20_cache_read_0_20`,
`tier_10_50_cache_read_0_25`). Re-verify before quoting; a stale row here rots every
derived ratio in this repo.

| Model | id | In | Out | Context | Output ratio |
|---|---|--:|--:|--:|:--:|
| Haiku 4.5 | `claude-haiku-4-5` | $1 | $5 | **200K** | **1×** |
| Sonnet 5 | `claude-sonnet-5` | $2 | $10 | 1M | **2×** |
| Opus 5.5 | `claude-opus-5-5` | $4 | $20 | 1M | 4× |
| Opus 5 | `claude-opus-5` | $5 | $25 | 1M | **5×** |
| Fable 5.1 | `claude-fable-5-1` | $10 | $50 | 1M | **10×** |

The number to reason with is the output ratio: **Haiku 1× / Sonnet 2× / Opus 4–5× /
Fable 10×**. The `opus` alias covers two priced rows; when that matters to a
budget, pin the full id in agent frontmatter (`model: claude-opus-5`). Haiku's
200K context is a *hard* constraint, not a soft cost — the only row in the table
that can fail outright rather than merely cost more.

**Cache reads are not uniformly 0.1× input.** Opus 5.5 bills them at **0.20×** and
Fable 5.1 at **0.25×** (the `cache_read_0_20` / `cache_read_0_25` tiers above); the others
use the standard ~0.1×. This matters wherever input dominates, and it sharpens the advisor
argument below: a Fable advisor's *cached* input costs 2.5× the usual fraction.

## Worked spend: a 10-agent fan-out

Assumptions, stated so you can substitute your own:

- 10 agents, one task each, all cold starts (subagents never inherit conversation)
- each agent **~40K input** (CLAUDE.md + system + task prompt + reads and tool
  results accumulated over the run) and **~5K output** → 400K in, 50K out

```
batch $ = (400K/1M x in_rate) + (50K/1M x out_rate)
```

| All 10 on | Input $ | Output $ | **Batch $** |
|---|--:|--:|--:|
| Haiku 4.5 | 0.40 | 0.25 | **0.65** |
| Sonnet 5 | 0.80 | 0.50 | **1.30** |
| Opus 5.5 | 1.60 | 1.00 | **2.60** |
| Opus 5 | 2.00 | 1.25 | **3.25** |
| Fable 5.1 | 4.00 | 2.50 | **6.50** |

Two things fall out that guessing does not give you. **Input dominates for
tool-using agents** — at 8:1 in:out, ~60% of the bill is input, so narrowing what
each agent reads moves the number more than dropping a tier does. And **the
absolute numbers are small**: a ten-way Opus fan-out is about three dollars, so
the decision worth your attention is whether the fan-out happens at all, not which
tier runs it.

## The effort x model grid

Rows are effort, columns are model.

**Effort is not free, and the column multipliers alone will mislead you.** The harness
carries a per-model effort cost index (read from the Claude Code 2.1.286 catalog,
`effort_cost_index`):

| model | low | medium | high | xhigh | max |
|---|--:|--:|--:|--:|--:|
| Sonnet 5 | 0.47 | 0.74 | 1 | **2.41** | **5.59** |
| Opus 5 | 0.67 | 0.76 | 1 | 1.6 | 1.7 |
| Fable 5.1 | 0.75 | 0.86 | 1 | 1.38 | 1.74 |
| Opus 5.5 | *(no index published)* | | | | |
| Haiku 4.5 | *(none — accepts no effort)* | | | | |

Multiply the column ratio by the index before comparing two cells. The consequences are
not small: **sonnet @ xhigh ≈ 2 × 2.41 = 4.8 effective units against opus @ high at 5.0** —
a wash, not a saving. Sonnet @ max ≈ 11, i.e. above Fable @ high. Opus is comparatively
flat across effort (1.7 at max) where Sonnet is steep.

| | haiku (1×) | sonnet (2×) | opus (4–5×) | fable (10×) |
|---|---|---|---|---|
| **low** | ⬜ n/a — the whole haiku column is "model default"; Haiku accepts no effort setting, see "Two things that break the table above" | ✅ cheap bulk drafting | ⚠️ pays for a ceiling it throttles | ❌ incoherent |
| **medium** | ⬜ n/a | ✅ the `worker` default | ⚠️ usually beaten by sonnet@xhigh | ❌ incoherent |
| **high** | ⬜ n/a | ✅ **`inspector` (read-only) and `drafter` (writes)** — pinned to the 2× column, ~2.0 effective units. The default rung for both verification and generation | ✅ strong for hard analysis — and where `reviewer`/`builder` land in an Opus session, at ~5.0 effective units | ⚠️ only if opus@xhigh already failed |
| **xhigh** | ⬜ n/a | ✅ coding / long-horizon | ✅ the `judge` tier | ⚠️ last resort |
| **max** | ⬜ n/a | ⚠️ | ✅ one contested call | ⚠️ |

Why the marked cells are mistakes:

- **The haiku column is not a set of mistakes — it does not exist.** There is no "haiku at
  xhigh" to avoid and no `low` to select; the basis is below. If a Haiku task needs more
  thoroughness, the task is not mechanical — promote the *model*, because raising effort is
  not available to you there.
- **fable @ low / medium.** Paying 10× for the strongest available reasoning and then
  capping it. Fable is only defensible at high or xhigh, on a task where opus @ xhigh has
  already been tried and was not good enough. (Note what the index above does to the usual
  phrasing of this point: opus @ high at 5.0 effective units and sonnet @ xhigh at ~4.8 are
  near-identical in cost, so neither "dominates" the other — pick on whether the task is
  capability-bound or thoroughness-bound, not on price.)
- **opus @ low.** Opus's advantage is extended reasoning; at low effort you buy a
  5× token price for a terser answer.
- **`reviewer` is `inherit` @ high** on purpose: finding defects repays effort far
  more than raw capability, so its cell moves with the session model. **The corollary
  is a cost trap:** on an Opus session every inherit tier — `reviewer`, `builder` — runs
  at Opus rates, so choosing one of them saves nothing. Selecting a tier feels like a
  cost decision and is not one. Measured 2026-09-30: a 19-agent fan-out
  passed `agentType: 'intelligent-delegate:reviewer'` on all 18 of its review and inventory
  calls (the 19th was the `judge` consolidation stage, which pins Opus regardless) and ran
  19/19 on `claude-opus-5`; a sibling 81-agent run that passed no `agentType` at all
  produced the identical all-Opus outcome. Correct tier usage and no tier usage cost the
  same. It happened a third time on 2026-10-08, across four scripts — see
  `workflow-patterns.md` → "Measured".

- **That trap is why 0.3.0 ships `inspector` and `drafter`,** and the grid above now shows
  why it was a real hole rather than a documentation gap. The sonnet/high cell is **2 × 1 =
  2.0 effective units**; `reviewer`/`builder` in an Opus session are **4–5 × 1 = 4–5**. So
  the pinned pair is a 2–2.5× saving at *the same effort level* — the "lower effort before
  lowering model" trade this file recommends, except here it is "same effort, lower model",
  which keeps the thoroughness and gives up only capability the stage did not need.
  **The assumption in that comparison, stated because it is not free:** each model's index
  is normalised to *its own* `high`, so multiplying column × index only compares across
  models if the two emit roughly the same number of output tokens at `high`. Nothing here
  measures that. If Sonnet is more verbose at high effort than Opus is, the real saving is
  smaller than 2–2.5×. Opus 5.5 also publishes no index at all, so its row assumes 1.
  Note the direction of the Sonnet index: going *up* from sonnet/high to sonnet/xhigh costs
  2.41×, landing at ~4.8 — level with opus/high. So **sonnet/high is the efficient Sonnet
  cell**, and if a stage genuinely needs more than it, escalating the model is no more
  expensive than escalating Sonnet's effort. That is the whole argument for this rung.

## "Best model at lower effort" vs a multi-model cascade

The tempting shape is a cascade: haiku drafts, sonnet fixes, opus adjudicates.
Measure the single-model alternative — **the best model you can afford, at lower
effort** — before building one.

- **Caches are model-scoped.** A cascade forfeits cache reuse across its models:
  each tier warms its own prefix of CLAUDE.md, the system prompt and the shared
  task context from cold. A homogeneous fan-out shares one prefix across every
  agent in it. The more agents and the larger the shared preamble, the more the
  cascade's structural disadvantage grows — and per the arithmetic above, input is
  the majority of the bill.
- **Handoffs cost tokens twice.** Every stage boundary is a summary written by one
  agent and re-read as input by the next — overhead a single agent never pays.
- **Cascades multiply failure modes.** A weak first stage produces confidently
  wrong scaffolding later stages repair rather than replace.

Build a cascade when the stages are *genuinely different kinds of work* — a
mechanical extraction pass feeding one hard judgment call — not as a cost trick.

## Cost per completed task, not per request

Judge the tier on what it costs to reach an accepted result.

Per-agent cost at the assumptions above is **$0.065 haiku / $0.13 sonnet / $0.26
opus 5.5 / $0.325 opus 5**. Ignoring the cost of noticing the failure, Haiku stops
being cheaper than a Sonnet one-shot at **2 attempts**, and than a one-shot on the
`opus` alias at **4 attempts** (Opus 5.5) or **5** (Opus 5). Add
a review pass per attempt and both break-evens move in sharply, because the review
is paid every attempt while the one-shot pays it once.

Symptoms that a cheap tier is silently costing more: repeated "close but wrong"
returns on one task shape; the caller rewriting the output instead of using it;
turns burned re-reading files; a `maxTurns` ceiling being hit.

**What to do:** sample 5–10 real tasks of that shape and count first-pass
acceptance. Below roughly 70%, promote and re-measure; above it, hold and spend
the attention on prompt and context instead. Promote the *model* for capability
failures (wrong approach, missed implications); raise the *effort* for
thoroughness failures (right approach, incomplete work).

## The Haiku 200K context trap

200K is a hard wall, and an agent's own tool output counts against it. Mechanical
does not mean small. Task shapes that look perfect for Haiku and are not:

- whole-file reads of any large file, or "read these N files and …"
- long logs, transcripts, diffs, or command output piped into context
- "survey the repo, then …" — the survey blows the window before the *then*
- multi-file refactors, where every edited file is read, echoed back, and retained
- any open-ended loop over discovered items

`Explore` is the shape that stays small: it reads *excerpts*, not whole files, and
omits CLAUDE.md. Use it to locate code — it does not review or audit it.

Rule: if you cannot bound how much text the agent will read, do not route it to
Haiku regardless of how mechanical it looks.

## The tool surface is the biggest lever

Single paired run on this harness, 2026-09-30 — same model (`haiku` pinned on both),
same prompt, identical output. **Two things differ between the arms**, tool count *and*
`omitClaudeMd`, so the gap is their joint effect:

| agent | tools | cold-start prefix | total input, 9 requests |
|---|--:|--:|--:|
| `mechanical` (6 tools, `omitClaudeMd: true`) | 6 | 7.5k | **98k** |
| `general-purpose` (all tools) | all | 42.4k | **435k** |

**4.4× on one task** (n=1 per arm — treat it as the order of magnitude, not a constant).
Two ratios appear above and they measure different things: the cold-start *prefix* ratio is
42.4/7.5 = **5.65×**, while **4.4×** is total input over 9 requests, which dilutes the fixed
prefix with accumulated tool results. Tool schemas are re-sent every request, so the gap
compounds with turn count; CLAUDE.md is only ~500 tokens of it, by subtraction rather than
by a third arm. Dropping Haiku→nothing saves less than trimming an all-tools agent to the
six tools it needs — note those levers multiply rather than compete. Scope `tools:` before
you touch model or effort.

## Two things that break the table above

**Haiku takes no effort setting.** Haiku 4.5 does not accept a reasoning-effort
parameter; the harness drops it silently. Every `haiku` cell in the effort grid is
therefore "model default", not the effort named — and shipping `effort:` on a Haiku
agent definition produces a knob that reads as tuned and does nothing. **Basis:** the
Claude Code 2.1.286 model catalog gives `claude-haiku-4-5` the capability list
`["context_management"]` — no `"effort"` — while `claude-sonnet-5`, `claude-opus-5` and
`claude-fable-5-1` each carry `"effort"`, `"xhigh_effort"` and `"max_effort"`, and Haiku
alone has no `effort_cost_index`. (Our own Haiku transcripts record no effort either, but
that is *not* evidence: `mechanical` never declares one, so absence is what you would
observe either way. The catalog is the falsifiable source.)

**An advisor re-prices every row.** When a session has an advisor configured, each
subagent receives it — observed 2026-09-30 in one session as `claude-fable-5-1` at 10×,
injected into every tier including `mechanical`. The advisor *model* is session
configuration, not a harness constant: the catalog assigns each model an `advisor_rank`,
so another session resolves a different one. Price the floor at whatever your own session
resolved. A single consult from a 1× agent costs more than the agent.
Treat this table as the floor: it is what the tier costs if nothing escalates. The
controls are session-wide — `/advisor off`, or `CLAUDE_CODE_DISABLE_ADVISOR_TOOL=1` for
scripted runs; a model reading this cannot issue either, so **ask the user**. Per-agent
suppression is not exposed through any documented surface: read in Claude Code 2.1.286,
the advisor spec is pushed onto the wire `tools` array *after* the client list and executes
server-side, so it never reaches an agent's allow/deny filter and a `disallowedTools` entry
for it is inert. The attachment is gated on a resolved advisor model plus internal
`advisorActive`/`advisorDeferred` flags that no agent-definition key reaches. Bundle
internals rot fast — re-check on CLI upgrades.

## Reaching MCP tools from a tier, and reading the error when you cannot

MCP tools arrive **deferred**: the schema is not loaded and `ToolSearch` is the documented
loader. Since `tools:` is an allowlist that *replaces* the default set, a tier that does not
list `ToolSearch` cannot load any MCP tool. `worker`, `drafter`, `inspector`, `reviewer`,
`builder` and `judge`
therefore list it. `mechanical` deliberately does not — MCP responses are unbounded and it
has a hard 200K wall; an MCP task is not a mechanical task.

**Listing it is necessary, not sufficient — verified 2026-10-01.** A probe run as
`reviewer` tried to reach MCP and got:

```
Error: No such tool available: ToolSearch. ToolSearch is disabled for this
session, in subagents as well as here.
```

A session can disable `ToolSearch` outright, and the disable **propagates into subagents**.
When that is in force, no tier reaches MCP whatever its allowlist says, and the fix is at the
session/permission layer, not in a definition. The same probe found no `mcp__*` tool exposed
to the subagent at all, loaded or deferred.

**The error text tells you which of three cases you are in.** This is the fastest diagnostic
available and the three have different fixes:

| what you see | what it means | where the fix is |
|---|---|---|
| bare `No such tool available: X`, no explanation | the name is not registered — wrong name, or that server is not configured for the session | the name, or the session's MCP config |
| `No such tool available: X. X is disabled for this session, in subagents as well as here.` | session-level disable, inherited by every subagent | session / permissions — ask the user |
| `No such tool available: X. X is not available in this session — <workaround>` | session-level unavailability with a suggested substitute | use the substitute, or ask the user |

A tool missing only from a definition's `tools:` list is a fourth case; our probe could not
isolate it, because the session-level disable above masks it. Do not assume the two produce
the same message.

**Corollary, and it bites: a `tools:` entry for a tool the session has disabled is inert.**
All seven tiers list `Grep` and `Glob`. In a session where both were disabled, a 92-agent
fan-out made **zero** `Grep` and **zero** `Glob` calls — the whole census was
`Bash 1524, Read 45, StructuredOutput 78, Write 1`, with every search done through `Bash`.
The declarations read as capabilities and were not, which is the same failure class as a
`disallowedTools` line sitting under an allowlist: a line that looks like a control and is
not one. When a fan-out behaves as though a tool does not exist, check whether it does before
concluding the agents chose otherwise.

**`mcpServers` is a legal agent-frontmatter key** (it sits in the accepted set alongside
`tools`, `model`, `effort`, `maxTurns`, `omitClaudeMd`), and is the declared channel for
giving one agent its own MCP servers. This plugin ships no tier that uses it, and we have not
tested whether it bypasses a session-level `ToolSearch` disable — so treat it as the place to
look, not as a known workaround.

## How to set each knob

| Where | model | effort | maxTurns | omitClaudeMd | tools |
|---|---|---|---|---|---|
| `Agent` tool | ✅ `haiku`\|`sonnet`\|`opus`\|`fable` | ❌ **none** | ❌ | ❌ | ❌ |
| Workflow `agent(prompt, opts)` | ✅ same tiers; omit to inherit session | ✅ `low`→`max` | ❌ | ❌ | ❌ |
| Agent definition frontmatter | ✅ alias, full id, or `inherit` | ✅ `low`→`max`, or an integer | ✅ | ✅ | ✅ **biggest lever** |
| `SKILL.md` frontmatter | ❌ | ⚠️ sets *this turn*, never a subagent (see below) | ❌ | ❌ | `allowed-tools` |

```js
// Workflow — the VERIFIED route to effort: "max", and the only way to vary it per call.
// Frontmatter `effort: max` is schema-legal too (see agent-catalog.md), but whether the
// runtime honours it from frontmatter is unconfirmed — so prefer this when it matters.
await agent(prompt, { model: "opus", effort: "max", label: "adjudicate" });
```
```markdown
<!-- agents/worker.md, as shipped — how an effort choice becomes reachable from Agent -->
---
name: worker
model: sonnet
effort: medium
maxTurns: 25
---
```

`worker` is the example here, not `mechanical`: a Haiku definition can demonstrate model
pinning but never effort pinning.

Then `Agent({ subagent_type: "intelligent-delegate:worker", ... })` gets both
the model and the effort, which a bare `Agent` call cannot express — **this
indirection is the mechanical point of the plugin.** (`:worker`, not `:mechanical`, for
the reason just given: the Haiku tier has no effort to carry.) Plugin agents are namespaced;
bare `mechanical` resolves only for a project-local `.claude/agents/mechanical.md`.

`SKILL.md` frontmatter: `effort:` there **is** honoured by this harness — the release
notes record fixing it being ignored on some models, which only makes sense for a
supported key. But it sets **the invoking turn's** effort, never a subagent's, so it is
not a delegation lever. It is also **not in the published Agent Skills spec** — which
allows only `name`, `description`, `license`, `allowed-tools`, `metadata`, and
`compatibility` — so the official `skill-creator` validator rejects it and the skill
stops being portable. That is why this plugin puts its tiering in `agents/*.md`, where
`effort:` is both documented and spec-legal.
