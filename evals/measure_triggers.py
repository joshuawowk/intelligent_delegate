#!/usr/bin/env python3
"""Measure whether the skill in THIS CHECKOUT actually fires, on real `claude -p` sessions.

Unlike skill-creator's run_eval.py — which tests a throwaway stub command and
scored 0/32 here while the real skill was firing — this drives the plugin itself
and records which Skill tool call (if any) each query produced.

Which copy it measures is not left to the install. Every call passes
`--plugin-dir <this repo>`, and every session's own init event is read back to
confirm the path it loaded `intelligent-delegate` from. A call that loaded any
other copy is an ERROR, not a hit or a miss.

That check replaced a sentence. Earlier versions printed "measuring the WORKING
TREE", on the strength of a 2026-10-01 probe of a local-path install. On a machine
where the plugin is a synced copy that sentence was false, nothing tested it, and
the run would have reported a clean measurement of the previous release.

Usage:  env -u CLAUDECODE python3 evals/measure_triggers.py
        env -u CLAUDECODE python3 evals/measure_triggers.py --runs 3 --out /tmp/run.json
        env -u CLAUDECODE python3 evals/measure_triggers.py -v   # per-trial detail
Reads evals/trigger-evals.json. Spawns one `claude -p` per query per run (billed).
Exit status: 0 only if every case matched its expectation and no case errored.
"""
import os, json, subprocess, sys, argparse, tempfile, shutil, time
import concurrent.futures as cf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ID = 'intelligent-delegate:delegate'   # kebab; the plugin id, not the repo dir name

ap = argparse.ArgumentParser()
ap.add_argument('--runs', type=int, default=int(os.environ.get('RUNS_PER_QUERY', '3')),
                help='trials per query; must be >=1, and odd so a tie is impossible')
ap.add_argument('--out', default=None, help='where to write results (default: a temp file, '
                'copied over evals/last-trigger-run.json only on a clean run)')
ap.add_argument('--allow-stale', action='store_true',
                help='accepted for compatibility and ignored: the working tree is loaded '
                     'explicitly, so there is no stale install to allow')
ap.add_argument('--timeout', type=int, default=300,
                help='per-call timeout. Measured: 150s with 6-way concurrency timed out 7 of '
                     '18 calls — and a timeout counted as a miss is exactly how a slow API '
                     'gets misread as a description regression.')
ap.add_argument('--concurrency', type=int, default=4,
                help='parallel `claude -p` calls. Higher contends for the API and inflates '
                     'per-call latency, which shows up as timeouts.')
ap.add_argument('-v', '--verbose', action='store_true',
                help='in the summary, print each query in full plus a per-trial breakdown: '
                'every error untruncated, and which skills fired instead on a miss')
args = ap.parse_args()

if args.runs < 1:
    sys.exit('--runs must be >= 1')
if args.runs % 2 == 0:
    print(f"WARNING: --runs {args.runs} is even; a {args.runs//2}-of-{args.runs} split counts "
          f"as NOT firing, since a query must fire in more than half its runs. Prefer an odd n.",
          file=sys.stderr)

QUERIES = json.load(open(REPO + '/evals/trigger-evals.json'))
seen = {}
for q in QUERIES:
    if q['query'] in seen:
        sys.exit(f"duplicate query in trigger-evals.json, results would be merged: {q['query']!r}")
    seen[q['query']] = True
if not any(q.get('control') for q in QUERIES):
    print("WARNING: no control case in trigger-evals.json. Without a must-fire and a "
          "must-not-fire control, a broken harness and a real regression look identical.",
          file=sys.stderr)

# --- what are we actually measuring? ------------------------------------------------
PLUGIN = 'intelligent-delegate'
HERE_REAL = os.path.realpath(REPO)
head = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD'],
                      capture_output=True, text=True).stdout.strip()
dirty = subprocess.run(['git', '-C', REPO, 'status', '--porcelain', '--', 'skills', 'agents',
                        '.claude-plugin'], capture_output=True, text=True).stdout.strip()

print(f"working tree HEAD   : {head}{'  (+ uncommitted changes to skills/, agents/ or the manifest)' if dirty else ''}")
print(f"loading             : --plugin-dir {REPO} on every call")
print("verifying           : each session's init event names the path it loaded the plugin "
      "from;")
print("                      a call that loaded any other copy is reported as an ERROR")

env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}

def run(job):
    item, _ = job
    try:
        p = subprocess.run(['claude', '-p', item['query'], '--plugin-dir', REPO,
                            '--output-format', 'stream-json', '--verbose'],
                           capture_output=True, timeout=args.timeout, env=env, cwd=REPO)
    except subprocess.TimeoutExpired:
        return {**item, 'fired': None, 'error': f'timeout after {args.timeout}s', 'skills': [],
                'loaded': None}
    if p.returncode != 0:
        tail = p.stderr.decode('utf-8', 'replace').strip().splitlines()[-3:]
        return {**item, 'fired': None, 'loaded': None,
                'error': f'claude exited {p.returncode}: ' + ' | '.join(tail), 'skills': []}
    skills = []
    loaded = None          # path this session loaded the plugin from; None = not reported
    for line in p.stdout.decode('utf-8', 'replace').splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict) and r.get('type') == 'system' and r.get('subtype') == 'init':
            for pl in r.get('plugins') or []:
                if isinstance(pl, dict) and pl.get('name') == PLUGIN:
                    loaded = pl.get('path') or '?'
            if loaded is None and 'plugins' in r:
                loaded = '(not loaded)'
        def walk(o):
            if isinstance(o, dict):
                if o.get('type') == 'tool_use' and o.get('name') == 'Skill':
                    skills.append(str((o.get('input') or {}).get('skill', '?')))
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(r)
    if not skills and not p.stdout.strip():
        return {**item, 'fired': None, 'error': 'claude produced no output', 'skills': [],
                'loaded': loaded}
    # The session says where it loaded the plugin from. Anything but this checkout means
    # the call measured some other copy, and its hit or miss is about that copy.
    if loaded is not None and os.path.realpath(loaded) != HERE_REAL:
        return {**item, 'fired': None, 'skills': skills, 'loaded': loaded,
                'error': f'session loaded {PLUGIN} from {loaded}, not from this checkout'}
    return {**item, 'fired': SKILL_ID in skills, 'error': None, 'skills': skills,
            'loaded': loaded}

jobs = [(q, i) for q in QUERIES for i in range(args.runs)]
total = len(jobs)
print(f"running {total} calls ({len(QUERIES)} queries x n={args.runs}), "
      f"concurrency {args.concurrency}, {args.timeout}s timeout", flush=True)
print(f"each line below is one COMPLETED call — this run bills {total} `claude -p` "
      f"invocations", flush=True)

# as_completed, not ex.map: ex.map returns an iterator that yields in submission order, so a
# single slow early call blocks every later result and the run prints nothing until the end.
# A billed run has to show progress while it is spending.
raw = []
t0 = time.monotonic()
with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
    futures = {ex.submit(run, j): j for j in jobs}
    for fut in cf.as_completed(futures):
        r = fut.result()
        raw.append(r)
        n = len(raw)
        el = time.monotonic() - t0
        eta = (el / n) * (total - n)
        if r['error']:
            mark = 'ERR '
            detail = r['error'][:60]
        else:
            mark = 'fire' if r['fired'] else '  . '
            detail = ','.join(r['skills']) or '(no Skill call)'
        print(f"  [{n:>3}/{total}] {mark} {el:6.0f}s elapsed, ~{eta:.0f}s left | "
              f"{r['query'][:44]:<44} | {detail[:48]}", flush=True)

from collections import defaultdict
agg = defaultdict(list)
for r in raw:
    agg[r['query']].append(r)

out = []
for q in QUERIES:
    rs = agg[q['query']]
    errs = [r['error'] for r in rs if r['error']]
    ok = [r for r in rs if r['error'] is None]
    hits = sum(1 for r in ok if r['fired'])
    # a query with ANY error is ERROR, not a miss: a dead harness must not read as a regression
    state = 'ERROR' if errs else ('FIRED' if hits / len(ok) > 0.5 else 'NOT_FIRED')
    out.append({**q, 'state': state, 'fired': state == 'FIRED',
                'rate': f"{hits}/{len(ok)}" if ok else '0/0',
                'skills_observed': sorted({s for r in ok for s in r['skills']}),
                'errors': errs,
                'loaded_from': sorted({str(r.get('loaded')) for r in rs}),
                'harness': {'runs': args.runs, 'head': head, 'dirty': bool(dirty),
                            'skill_id': SKILL_ID}})

dest = args.out or os.path.join(tempfile.mkdtemp(prefix='trigger-run-'), 'run.json')
json.dump(out, open(dest, 'w'), indent=1)

errored = [r for r in out if r['state'] == 'ERROR']
bad = [r for r in out if r['state'] != 'ERROR' and r['fired'] != r['should_trigger']]
ctl_bad = [r for r in out if r.get('control') and r['state'] != 'ERROR'
           and r['fired'] != r['should_trigger']]

tp = sum(1 for r in out if r['should_trigger'] and r['fired'] and r['state'] != 'ERROR')
fn = sum(1 for r in out if r['should_trigger'] and not r['fired'] and r['state'] != 'ERROR')
fp = sum(1 for r in out if not r['should_trigger'] and r['fired'] and r['state'] != 'ERROR')
tn = sum(1 for r in out if not r['should_trigger'] and not r['fired'] and r['state'] != 'ERROR')
unconfirmed = sum(1 for r in raw if r['error'] is None and r.get('loaded') is None)
confirmed = sum(1 for r in raw if r['error'] is None and r.get('loaded') is not None)
print(f"loaded from this checkout, confirmed by the session: {confirmed} of {len(raw)} calls")
if unconfirmed:
    print(f"WARNING: {unconfirmed} call(s) reported no plugin list in their init event, so which "
          f"copy they loaded is UNCONFIRMED. The CLI's stream-json shape may have changed.",
          file=sys.stderr)
print(f"TP={tp} FN={fn} FP={fp} TN={tn} ERROR={len(errored)}")
print(f"(n={args.runs} per query; a query counts as firing above 50% of non-errored runs)")
for r in out:
    mark = 'ERR' if r['state'] == 'ERROR' else ('OK ' if r['fired'] == r['should_trigger'] else 'BAD')
    ctl = ' [control]' if r.get('control') else ''
    if args.verbose:
        print(f"  [{mark}] want={str(r['should_trigger']):5s} rate={r['rate']:>5s} | "
              f"{r['query']}{ctl}")
        # agg preserves job order, so these are in trial order
        for i, t in enumerate(agg[r['query']], 1):
            if t['error']:
                detail = 'ERROR ' + t['error']
            else:
                detail = ('fired' if t['fired'] else 'did not fire')
                detail += ' | skills: ' + (', '.join(t['skills']) or '(none)')
            print(f"        trial {i}/{args.runs}: {detail}")
    else:
        print(f"  [{mark}] want={str(r['should_trigger']):5s} rate={r['rate']:>5s} | "
              f"{r['query'][:58]}{ctl}")
        for e in r['errors'][:1]:
            print(f"        error: {e[:150]}")
print(f"results: {dest}")

if ctl_bad:
    print("CONTROL CASE FAILED — treat every other number in this run as unreliable.", file=sys.stderr)
# Archiving and exit status are SEPARATE questions. A run with no ERRORs produced valid
# data even if a case missed, so it is worth archiving; a mismatch is still a non-zero exit
# because the description regressed. Only a run that errored is untrustworthy data.
canon = os.path.join(REPO, 'evals', 'last-trigger-run.json')
# Archive unless the run is wholly uninterpretable. 17 of 18 cases measured at n=3 with one
# timeout is useful data; withholding it was the same over-strictness as the old SHA guard.
# Errored cases are visible in the artifact as state == "ERROR", so nothing is hidden.
if not args.out and len(errored) < len(out):
    payload = {'_README': ('Generated by evals/measure_triggers.py. Real run, not a stub. '
                           'See evals/README.md for how to read it.'),
               'generated_utc': __import__('datetime').datetime.now(
                   __import__('datetime').timezone.utc).isoformat(timespec='seconds'),
               'runs_per_query': args.runs, 'head': head, 'dirty': bool(dirty),
               'loaded_from': HERE_REAL, 'calls_confirmed': confirmed,
               'calls_unconfirmed': unconfirmed, 'skill_id': SKILL_ID,
               'totals': {'TP': tp, 'FN': fn, 'FP': fp, 'TN': tn, 'ERROR': len(errored)},
               'results': out}
    json.dump(payload, open(canon, 'w'), indent=1)
    print(f"archived to {canon}" + (f" — {len(errored)} errored case(s) are in it as state ERROR, "
          f"outside the totals" if errored else " (no errored cases)"))
elif errored:
    print(f"NOT archived: every case errored, so this run measured nothing. Raw output "
          f"kept at {dest}", file=sys.stderr)

if errored or bad:
    print(f"FAIL: {len(errored)} errored, {len(bad)} mismatched expectation.", file=sys.stderr)
    sys.exit(1)
