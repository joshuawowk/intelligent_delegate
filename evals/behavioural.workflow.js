export const meta = {
  name: 'skill-behavioural-evals',
  description: 'Run each routing eval case 3 times against the rewritten skill, grade each answer against that case\'s expectations',
  phases: [
    { title: 'Answer', detail: 'stand in for the main loop with the skill loaded; read-only' },
    { title: 'Grade', detail: 'each expectation pass/fail with quoted evidence', model: 'sonnet' },
  ],
}

// Pass args: {repo: '<absolute path to this checkout>', reps: 3, cases: [{id, prompt}, ...]}
// where cases are the id and prompt of each entry in evals/evals.json — and nothing else.
// The answering agent must never see `expectations`; print the list with:
//   python3 -c "import json;print(json.dumps([{'id':e['id'],'prompt':e['prompt']} for e in json.load(open('evals/evals.json'))['evals']]))"
const REPO = args && args.repo
if (!REPO) throw new Error('args.repo is required: the absolute path of this checkout')
const cases = (args && args.cases) || []
const reps = (args && args.reps) || 3
if (!cases.length) throw new Error('args.cases is required: [{id, prompt}]')

const GRADED = {
  type: 'object',
  properties: {
    case_id: { type: 'integer' },
    results: { type: 'array', items: { type: 'object', properties: {
      expectation: { type: 'string' }, passed: { type: 'boolean' }, evidence: { type: 'string' } },
      required: ['expectation', 'passed', 'evidence'] } },
  },
  required: ['case_id', 'results'],
}

function answerPrompt(c) {
  return [
    'You are standing in for the main loop of a Claude Code session: model Opus 5.5 at effort xhigh, with the',
    'intelligent-delegate plugin installed. Its `delegate` skill has just loaded in response to the user message below.',
    '',
    'The skill\'s text is ' + REPO + '/skills/delegate/SKILL.md. Read it in full now, exactly as if it had been loaded',
    'into your context. Read a file under ' + REPO + '/skills/delegate/references/ only if the skill body sends you',
    'there for this question.',
    '',
    'Read NOTHING else in that repository. In particular nothing under evals/ or docs/, and not CHANGELOG.md or README.md:',
    'they hold the rubric this answer is graded against, and reading them voids the run.',
    '',
    'Then answer the user as you would in that session: say what you would do and why, resting on the skill\'s own rules.',
    'Do not spawn agents and do not run a workflow — describe the routing, do not perform it. Under 350 words.',
    'Your final message is the answer itself, with no preamble.',
    '',
    'USER MESSAGE:',
    c.prompt,
  ].join('\n')
}

function gradePrompt(answer, c) {
  return [
    'Grade one answer against a fixed rubric.',
    '',
    'The rubric is case id ' + c.id + ' in ' + REPO + '/evals/evals.json: read that file and use ONLY that case\'s `expectations` list',
    '(its `expected_output` is context for what a good answer looks like, not something to grade).',
    '',
    'For EACH expectation, in order, decide passed true or false:',
    '  - true only if the answer actually says it. Do not credit what it merely implies or what a charitable reader could infer.',
    '  - an expectation phrased as "It does not ..." passes when the answer does not do that thing.',
    '  - an expectation phrased as "If it ..., it ..." passes when the condition does not arise, or arises and is handled as stated.',
    '  - evidence: a short verbatim quote from the answer that decides it, or a plain statement of what is missing.',
    'Do not grade style, length or tone. Do not modify any file.',
    '',
    'Return case_id ' + c.id + ' and one result per expectation, with the expectation text copied exactly.',
    '',
    'THE USER MESSAGE WAS:',
    c.prompt,
    '',
    'THE ANSWER TO GRADE:',
    '<<<',
    String(answer),
    '>>>',
  ].join('\n')
}

const items = []
for (const c of cases) for (let r = 1; r <= reps; r++) items.push({ id: c.id, prompt: c.prompt, rep: r })
log(items.length + ' answers (' + cases.length + ' cases x ' + reps + ') and as many gradings: ' + (2 * items.length) + ' agents. n=3 because a single run of a model-mediated check is noise.')

const out = await pipeline(
  items,
  // The main loop is the session model, so its stand-in inherits it. Read-only.
  it => agent(answerPrompt(it), { agentType: 'intelligent-delegate:reviewer', label: 'answer:' + it.id + ':' + it.rep, phase: 'Answer' }),
  // Checking an answer against a written rubric is the default inspection tier's job, at its new default effort.
  (answer, it) => {
    if (!answer || String(answer).trim().length < 40) { log('case ' + it.id + ' rep ' + it.rep + ': answer too short to grade (' + String(answer || '').length + ' ch)'); return { id: it.id, rep: it.rep, answer: answer, graded: null } }
    return agent(gradePrompt(answer, it), { agentType: 'intelligent-delegate:inspector', effort: 'medium', label: 'grade:' + it.id + ':' + it.rep, phase: 'Grade', schema: GRADED })
      .then(g => ({ id: it.id, rep: it.rep, answer: answer, graded: g }))
  },
)

const done = out.filter(Boolean)
if (done.length < items.length) log('WARNING: ' + (items.length - done.length) + ' run(s) died and are missing')
const summary = cases.map(c => {
  const runs = done.filter(d => d.id === c.id && d.graded)
  const n = runs.length
  const exp = n ? runs[0].graded.results.map(r => r.expectation) : []
  const per = exp.map((e, i) => ({ expectation: e.slice(0, 110), passed: runs.filter(r => r.graded.results[i] && r.graded.results[i].passed).length, of: n }))
  return { id: c.id, runs: n, all_pass_runs: runs.filter(r => r.graded.results.every(x => x.passed)).length, weak: per.filter(p => p.passed < p.of) }
})
return { cases: cases.length, reps: reps, graded: done.filter(d => d.graded).length, summary: summary }
