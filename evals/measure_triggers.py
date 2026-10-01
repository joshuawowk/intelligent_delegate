#!/usr/bin/env python3
"""Measure whether the INSTALLED skill actually fires, on real `claude -p` sessions.

Unlike skill-creator's run_eval.py — which tests a throwaway stub command and
scored 0/32 here while the real skill was firing — this drives the plugin as
installed and records which Skill tool call (if any) each query produced.

What it measures is the INSTALLED plugin, not the working tree. Those differ
whenever the plugin cache is stale, so this prints both and refuses to run on a
mismatch unless you pass --allow-stale. See evals/README.md.

Usage:  env -u CLAUDECODE python3 evals/measure_triggers.py
        env -u CLAUDECODE python3 evals/measure_triggers.py --runs 3 --out /tmp/run.json
Reads evals/trigger-evals.json. Spawns one `claude -p` per query per run (billed).
Exit status: 0 only if every case matched its expectation and no case errored.
"""
import os, json, subprocess, sys, argparse, tempfile, shutil
import concurrent.futures as cf

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ID = 'intelligent-delegate:delegate'   # kebab; the plugin id, not the repo dir name

ap = argparse.ArgumentParser()
ap.add_argument('--runs', type=int, default=int(os.environ.get('RUNS_PER_QUERY', '3')),
                help='trials per query; must be >=1, and odd so a tie is impossible')
ap.add_argument('--out', default=None, help='where to write results (default: a temp file, '
                'copied over evals/last-trigger-run.json only on a clean run)')
ap.add_argument('--allow-stale', action='store_true',
                help='run even if the installed plugin differs from the working tree')
ap.add_argument('--timeout', type=int, default=150)
args = ap.parse_args()

if args.runs < 1:
    sys.exit('--runs must be >= 1')
if args.runs % 2 == 0:
    print(f"WARNING: --runs {args.runs} is even; a {args.runs//2}-of-{args.runs} split counts "
          f"as firing. Prefer an odd n.", file=sys.stderr)

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

# --- what are we actually measuring? installed plugin vs working tree -------------
def installed_state():
    try:
        reg = json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json')))
    except Exception as e:
        return None, None, f'could not read installed_plugins.json: {e}'
    def walk(o):
        if isinstance(o, dict):
            if 'installPath' in o:
                yield o
            for v in o.values():
                yield from walk(v)
        elif isinstance(o, list):
            for v in o:
                yield from walk(v)
    for e in walk(reg):
        if 'intelligent-delegate' in str(e.get('installPath', '')):
            return e.get('installPath'), e.get('gitCommitSha'), None
    return None, None, 'intelligent-delegate not found in installed_plugins.json'

head = subprocess.run(['git', '-C', REPO, 'rev-parse', 'HEAD'],
                      capture_output=True, text=True).stdout.strip()
ipath, isha, ierr = installed_state()
print(f"working tree HEAD   : {head}")
print(f"installed plugin    : {isha or '?'}  ({ipath or ierr})")
if isha and head and not head.startswith(isha) and not isha.startswith(head):
    msg = ("MISMATCH: the installed plugin is not the working tree, so this run does NOT "
           "measure your edits. Refresh the install first (see evals/README.md).")
    if not args.allow_stale:
        sys.exit(msg + "  Pass --allow-stale to measure the installed copy anyway.")
    print("WARNING: " + msg, file=sys.stderr)

env = {k: v for k, v in os.environ.items() if k != 'CLAUDECODE'}

def run(job):
    item, _ = job
    try:
        p = subprocess.run(['claude', '-p', item['query'], '--output-format', 'stream-json',
                            '--verbose'],
                           capture_output=True, timeout=args.timeout, env=env, cwd=REPO)
    except subprocess.TimeoutExpired:
        return {**item, 'fired': None, 'error': f'timeout after {args.timeout}s', 'skills': []}
    if p.returncode != 0:
        tail = p.stderr.decode('utf-8', 'replace').strip().splitlines()[-3:]
        return {**item, 'fired': None,
                'error': f'claude exited {p.returncode}: ' + ' | '.join(tail), 'skills': []}
    skills = []
    for line in p.stdout.decode('utf-8', 'replace').splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
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
        return {**item, 'fired': None, 'error': 'claude produced no output', 'skills': []}
    return {**item, 'fired': SKILL_ID in skills, 'error': None, 'skills': skills}

jobs = [(q, i) for q in QUERIES for i in range(args.runs)]
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    raw = list(ex.map(run, jobs))

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
                'harness': {'runs': args.runs, 'head': head, 'installed_sha': isha,
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
print(f"TP={tp} FN={fn} FP={fp} TN={tn} ERROR={len(errored)}")
print(f"(n={args.runs} per query; a query counts as firing above 50% of non-errored runs)")
for r in out:
    mark = 'ERR' if r['state'] == 'ERROR' else ('OK ' if r['fired'] == r['should_trigger'] else 'BAD')
    ctl = ' [control]' if r.get('control') else ''
    print(f"  [{mark}] want={str(r['should_trigger']):5s} rate={r['rate']:>5s} | {r['query'][:58]}{ctl}")
    for e in r['errors'][:1]:
        print(f"        error: {e[:150]}")
print(f"results: {dest}")

if ctl_bad:
    print("CONTROL CASE FAILED — treat every other number in this run as unreliable.", file=sys.stderr)
# Archiving and exit status are SEPARATE questions. A run with no ERRORs produced valid
# data even if a case missed, so it is worth archiving; a mismatch is still a non-zero exit
# because the description regressed. Only a run that errored is untrustworthy data.
canon = os.path.join(REPO, 'evals', 'last-trigger-run.json')
if not args.out and not errored:
    payload = {'_README': ('Generated by evals/measure_triggers.py. Real run, not a stub. '
                           'See evals/README.md for how to read it.'),
               'generated_utc': __import__('datetime').datetime.now(
                   __import__('datetime').timezone.utc).isoformat(timespec='seconds'),
               'runs_per_query': args.runs, 'head': head, 'installed_sha': isha,
               'skill_id': SKILL_ID,
               'totals': {'TP': tp, 'FN': fn, 'FP': fp, 'TN': tn, 'ERROR': len(errored)},
               'results': out}
    json.dump(payload, open(canon, 'w'), indent=1)
    print(f"archived to {canon} (no errored cases, so the data is valid)")
elif errored:
    print(f"NOT archived: {len(errored)} case(s) errored, so this run's data is not "
          f"trustworthy. Raw output kept at {dest}", file=sys.stderr)

if errored or bad:
    print(f"FAIL: {len(errored)} errored, {len(bad)} mismatched expectation.", file=sys.stderr)
    sys.exit(1)
