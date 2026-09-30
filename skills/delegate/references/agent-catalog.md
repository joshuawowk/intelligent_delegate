# Agent catalog

Every value you can pass as `subagent_type`, and what it costs. Output-token cost is the
number to reason with: **Haiku 1x / Sonnet 2x / Opus 4-5x / Fable 10x** (the `opus` alias
spans Opus 5.5 at 4x and Opus 5 at 5x).

## The mechanism (read this first)

The Agent tool takes `prompt`, `subagent_type`, `description`, `model`, `isolation`,
`run_in_background`. Its `model` enum is exactly `sonnet | opus | haiku | fable`, and
**there is no `effort` parameter**. Effort is reachable in only two places: the `effort:`
key in an agent definition's frontmatter (`low|medium|high|xhigh`), and the Workflow
tool's `agent(prompt, {effort})` where `max` is also available.

So: *the only way to get a specific effort level out of the Agent tool is to pass the
name of a definition that pins it.* That is what the four definitions below exist for.
`SKILL.md` frontmatter is **not** a third lever: it does not set a subagent's effort —
only an agent definition does. (See `model-selection.md` for what `effort:` in `SKILL.md` does and does not do.)

Every subagent starts with **cold context** — it cannot see the conversation — and its
final report is **not shown to the user**, so the caller must relay it. Plugin agents are
namespaced: `intelligent_delegate:worker` when the bare name is ambiguous.

## Shipped by this plugin

| `subagent_type` | model | effort | maxTurns | output cost |
|---|---|---|---|---|
| `mechanical` | `haiku` | `low` | 12 | 1x |
| `worker` | `sonnet` | `medium` | 25 | 2x |
| `reviewer` | `inherit` | `high` | 20 | session model |
| `judge` | `opus` | `xhigh` | 15 | 4-5x |

### `mechanical` — haiku / low
- **Use when:** the work is fully specified, deterministic, and verifiable without judgment — renaming across files, applying a known pattern, extracting fields, running a checklist.
- **Do NOT use when:** the task needs a call between defensible alternatives, **or reads a lot** — Haiku's context is 200K, a hard ceiling that no amount of "but it's mechanical" overrides.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash; `Agent` disallowed.

### `worker` — sonnet / medium
- **Use when:** ordinary multi-step implementation or research that needs real comprehension but has a knowable right answer — a scoped feature, tracing a subsystem, tests against a clear spec. This is the default; reach for it unless something argues otherwise.
- **Do NOT use when:** the task is pure mechanical churn (pay 1x instead) or a contested judgment call where being confidently wrong is expensive.
- **Tools:** Read, Grep, Glob, Edit, Write, Bash, WebFetch, WebSearch; `Agent` disallowed.

### `reviewer` — inherit / high
- **Use when:** the job is *finding what is wrong* — code review, spec-versus-implementation diffs, adversarial verification of another agent's output. `high` is the sweet spot balancing quality and token efficiency, and `inherit` is deliberate: review quality should track the session model rather than being pinned below it.
- **Do NOT use when:** you want the defect fixed — this tier has no Edit or Write tools; route the fix to `worker` afterwards.
- **Tools:** Read, Grep, Glob, Bash; Edit, Write, Agent disallowed.

### `judge` — opus / xhigh
- **Use when:** adjudicating a contested call — two reviewers disagree, an architectural decision is irreversible, the cost of being wrong dominates the 4-5x token cost.
- **Do NOT use when:** there is a knowable right answer, or when you have not first measured whether `reviewer` at `high` already gets it. Do not fan `judge` out across many items.
- **Tools:** Read, Grep, Glob, Bash; Edit, Write, Agent disallowed.

## Built-ins

### `Explore`
Read-only fan-out search. Reads **excerpts, not whole files**, takes a breadth hint, and
**omits CLAUDE.md**, which makes its cold start cheaper than a custom definition's.
- **Good for:** locating things. Where is X defined, which files touch Y, what exists here.
- **NOT good for:** review, audit, or any verdict. Explore *locates* code; it does not
  judge it, and it never saw the whole file it quoted from. This is the routine misuse —
  an "Explore, and check whether the auth is sound" call returns confident-sounding
  findings drawn from excerpts. Locate with `Explore`, then judge with `reviewer`.
  Also not for anything that writes, and not for work needing project conventions,
  since it does not get CLAUDE.md.

### `Plan`
Architect. Returns step-by-step plans and the critical files, with **no write tools** and
no CLAUDE.md.
- **Good for:** turning a vague goal into an ordered plan before any code is touched.
- **NOT good for:** executing the plan, or verifying that existing code matches one.

### `general-purpose`
Full tool access, multi-step, open-ended.
- **Good for:** a task that genuinely needs everything and does not fit a tier.
- **NOT good for:** anything a tiered definition covers — it pins no effort, so you get
  the default, and you lose the tier's tool restrictions along with it. Preferring it by
  reflex is how the whole effort mechanism gets bypassed.

## Selection table

| Task shape | `subagent_type` | Why |
|---|---|---|
| "Where is X handled?" | `Explore` | Locating, not judging; cheapest cold start |
| "Plan the migration" | `Plan` | Architect, no write tools to misfire |
| Rename/reformat across N files | `mechanical` | Deterministic and verifiable; 1x |
| Same, but 400K of input | `worker` | Haiku's 200K context is a hard wall |
| Implement a scoped feature | `worker` | Comprehension with a knowable right answer |
| Trace how a subsystem works | `worker` | Needs whole files, not excerpts |
| Review a diff for defects | `reviewer` | No Edit/Write, `high`, tracks session model |
| Verify another agent's claim | `reviewer` | Adversarial read, no write authority |
| Two reviewers disagree | `judge` | Adjudication at 4-5x, once, not per item |
| Irreversible architectural call | `judge` | Cost of being wrong dominates spend |
| Doesn't fit any of the above | `general-purpose` | Last resort; no effort pinned |

## Two cost rules that override the table

1. **Judge cost per completed task, not per request.** A cheaper tier that needs three
   retries and a `reviewer` pass is not cheaper.
2. **Caches are model-scoped.** A cascade across models forfeits cache reuse between
   them — measure "best model at lower effort" before building one.
