import os
REPO=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#!/usr/bin/env python3
"""Measure whether the INSTALLED skill actually fires, on real `claude -p` sessions.

Unlike skill-creator's run_eval.py — which tests a throwaway stub command and
scored 0/32 here while the real skill was firing — this drives the plugin as
installed and records which Skill tool call (if any) each query produced.

Usage:  env -u CLAUDECODE python3 evals/measure_triggers.py
Reads evals/trigger-evals.json. Spawns one `claude -p` per query (billed).
"""
import json,subprocess,os,sys,concurrent.futures as cf
QUERIES=json.load(open('REPO/evals/trigger-evals.json'))
env={k:v for k,v in os.environ.items() if k!='CLAUDECODE'}
def run(item):
    q=item['query']
    try:
        p=subprocess.run(['claude','-p',q,'--output-format','stream-json','--verbose'],
                         capture_output=True,timeout=150,env=env,cwd='REPO')
    except subprocess.TimeoutExpired:
        return {**item,'fired':None,'skill':'TIMEOUT'}
    skills=[]
    for line in p.stdout.decode('utf-8','replace').splitlines():
        try: r=json.loads(line)
        except: continue
        def walk(o):
            if isinstance(o,dict):
                if o.get('type')=='tool_use' and o.get('name')=='Skill':
                    skills.append(str((o.get('input') or {}).get('skill','?')))
                for v in o.values(): walk(v)
            elif isinstance(o,list):
                for v in o: walk(v)
        walk(r)
    fired=any('delegate' in s for s in skills)
    return {**item,'fired':fired,'skill':','.join(skills) or '-'}
with cf.ThreadPoolExecutor(max_workers=6) as ex:
    out=list(ex.map(run,QUERIES))
json.dump(out,open(REPO+'/evals/last-trigger-run.json','w'),indent=1)
tp=sum(1 for r in out if r['should_trigger'] and r['fired'])
fn=sum(1 for r in out if r['should_trigger'] and not r['fired'])
fp=sum(1 for r in out if not r['should_trigger'] and r['fired'])
tn=sum(1 for r in out if not r['should_trigger'] and not r['fired'])
print(f"TP={tp} FN={fn} FP={fp} TN={tn}")
for r in out:
    mark='OK ' if r['fired']==r['should_trigger'] else 'BAD'
    print(f"  [{mark}] want={str(r['should_trigger']):5s} fired={str(r['fired']):5s} | {r['query'][:62]} | {r['skill'][:40]}")
