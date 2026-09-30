# Model and effort selection

Read this when a tier call is genuinely close — the skill body handles the easy
cases; this file prices the hard ones.

## Cost table

First-party API rates, USD per million tokens.

| Model | id | In | Out | Context | Output ratio |
|---|---|--:|--:|--:|:--:|
| Haiku 4.5 | `claude-haiku-4-5` | $1 | $5 | **200K** | **1×** |
| Sonnet 5 | `claude-sonnet-5` | $2 | $10 | 1M | **2×** |
| Opus 5.5 | `claude-opus-5-5` | $4 | $20 | 1M | 4× |
| Opus 5 | `claude-opus-5` | $5 | $25 | 1M | **5×** |
| Fable 5.1 | `claude-fable-5-1` | $10 | $50 | 1M | **10×** |

The number to reason with is the output ratio: **Haiku 1× / Sonnet 2× / Opus 5× /
Fable 10×**. The `opus` alias covers two priced rows; when that matters to a
budget, pin the full id in agent frontmatter (`model: claude-opus-5`). Haiku's
200K context is a *hard* constraint, not a soft cost — the only row in the table
that can fail outright rather than merely cost more.

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

Rows are effort, columns are model. `max` is reachable **only** from Workflow
`agent({effort: "max"})`; agent frontmatter tops out at `xhigh`.

| | haiku (1×) | sonnet (2×) | opus (5×) | fable (10×) |
|---|---|---|---|---|
| **low** | ✅ the `mechanical` tier | ✅ cheap bulk drafting | ⚠️ pays for a ceiling it throttles | ❌ incoherent |
| **medium** | ⚠️ borderline; prefer low or promote | ✅ the `worker` default | ⚠️ usually beaten by sonnet@xhigh | ❌ incoherent |
| **high** | ❌ wrong axis | ✅ the `reviewer` shape | ✅ strong for hard analysis | ⚠️ only if opus@xhigh already failed |
| **xhigh** | ❌ **the default trap** | ✅ coding / long-horizon | ✅ the `judge` tier | ⚠️ last resort |
| **max** (Workflow only) | ❌ | ⚠️ | ✅ one contested call | ⚠️ |

Why the marked cells are mistakes:

- **haiku @ xhigh — the default trap.** `xhigh` is the Claude Code default and the
  Agent tool has **no effort parameter**, so a bare `Agent(model: "haiku")` runs
  haiku at xhigh: the cheapest reasoning, told to reason as hard as it can. Effort
  raises thoroughness *within* one model; it does not lift a ceiling, so you pay
  extra tokens for output the model was never going to improve. This cell is why
  `agents/mechanical.md` exists — pass it as `subagent_type` and it supplies `low`.
- **haiku @ high.** Same error, smaller. If a haiku task needs more thoroughness,
  the task is not mechanical. Promote the model; do not raise the effort.
- **fable @ low / medium.** Paying 10× for the strongest available reasoning and
  then capping it. opus @ high (5×) or sonnet @ xhigh (2×) dominates: more actual
  thinking, less money. Fable is only defensible at high or xhigh, on a task where
  opus @ xhigh has already been tried and was not good enough.
- **opus @ low.** Opus's advantage is extended reasoning; at low effort you buy a
  5× token price for a terser answer.
- **`reviewer` is `inherit` @ high** on purpose: finding defects repays effort far
  more than raw capability, so its cell moves with the session model.

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

Per-agent cost at the assumptions above is **$0.065 haiku / $0.13 sonnet / $0.325
opus 5**. Ignoring the cost of noticing the failure, Haiku stops being cheaper
than a Sonnet one-shot at **2 attempts** and than an Opus 5 one-shot at **5**. Add
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

## How to set each knob

| Where | model | effort | maxTurns |
|---|---|---|---|
| `Agent` tool | ✅ `haiku`\|`sonnet`\|`opus`\|`fable` | ❌ **none** | ❌ |
| Workflow `agent(prompt, opts)` | ✅ same tiers; omit to inherit session | ✅ `low`→`max` | ❌ |
| Agent definition frontmatter | ✅ alias, full id, or `inherit` | ✅ `low`→`xhigh` | ✅ |
| `SKILL.md` frontmatter | ❌ | ❌ not a lever (see below) | ❌ |

```js
// Workflow — the only place effort: "max" is reachable
await agent(prompt, { model: "opus", effort: "max", label: "adjudicate" });
```
```markdown
<!-- agents/mechanical.md — how an effort choice becomes reachable from Agent -->
---
name: mechanical
model: haiku
effort: low
maxTurns: 12
---
```

Then `Agent({ subagent_type: "intelligent_delegate:mechanical", ... })` gets both
the model and the effort, which a bare `Agent` call cannot express — **this
indirection is the mechanical point of the plugin.** Plugin agents are namespaced;
bare `mechanical` resolves only for a project-local `.claude/agents/mechanical.md`.

`SKILL.md` frontmatter: some third-party plugins do set `effort:` and `maxTurns:`
there, but **neither key is in the published Agent Skills spec** — which allows
only `name`, `description`, `license`, `allowed-tools`, `metadata`, and
`compatibility` — and the official `skill-creator` validator rejects anything
else. Whether this harness silently honors them or silently ignores them is
**unverified**, so do not build a tiering decision on it. That is precisely why
this plugin puts its tiering in `agents/*.md`, where `effort:` *is* documented
behaviour, rather than in skill frontmatter.
