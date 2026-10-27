import json,sys
from pathlib import Path
from statistics import median
root=Path(sys.argv[1]);fixture=json.loads((root/'cases.json').read_text());cases={c['id']:c for c in fixture['cases']}
summary={}
for label in ['27b','q2','q3']:
 if not (root/(label+'.jsonl')).exists() or not (root/(label+'-text-review.json')).exists():continue
 rows=[json.loads(x) for x in (root/(label+'.jsonl')).read_text().splitlines()]
 reviews={(r['id'],r['seed']):r for r in json.loads((root/(label+'-text-review.json')).read_text())['grades']}
 outcomes=[]
 for r in rows:
  c=cases[r['id']];z=r['result'];wanted={json.dumps(o,sort_keys=True,ensure_ascii=False) for o in c['wanted']}
  failed={json.dumps(c['fail_target'],sort_keys=True,ensure_ascii=False)} if 'fail_target' in c else set()
  already=set()
  for op in wanted-failed:
   o=json.loads(op)
   for e in fixture['entities']:
    if e['name']==o['name'] and e['area']==o['area'] and (e['state']=='on' if o['kind']=='on' else e.get(o['kind']))==o['value']:already.add(op)
  bad=z['unwanted_or_invalid_calls'];unwanted=sum(x=='Unrequested action' for x in bad)
  no_tools_ok=not c.get('no_tools') or len(z['replies'])==1 and not z['replies'][0]['choices'][0]['message'].get('tool_calls')
  complete=set(z['done'])|already==wanted-failed and failed<=set(z['attempted'])
  text=reviews[(r['id'],r['seed'])]['text_pass']
  passed=complete and not unwanted and no_tools_ok and z['finished'] and text
  outcomes.append(dict(id=r['id'],seed=r['seed'],category=r['category'],passed=passed,actions_complete=complete,text_pass=text,unwanted_actions=unwanted,invalid_calls=sum(x not in ['No matching device','Unrequested action'] for x in bad),elapsed_s=z['elapsed_s'],first_action_s=z['first_action_s']))
 stats={cat:dict(passed=sum(o['passed'] for o in outcomes if o['category']==cat),total=sum(o['category']==cat for o in outcomes)) for cat in sorted({o['category'] for o in outcomes})}
 summary[label]=dict(passed=sum(o['passed'] for o in outcomes),total=len(outcomes),categories=stats,median_completion_s=median(o['elapsed_s'] for o in outcomes),unwanted_action_calls=sum(o['unwanted_actions'] for o in outcomes),unwanted_action_observations=sum(o['unwanted_actions']>0 for o in outcomes),invalid_calls=sum(o['invalid_calls'] for o in outcomes),outcomes=outcomes)
latency={}
if all((root/(k+'-latency.jsonl')).exists() for k in ['27b','q2','q3']):
    probes={k:{(r['id'],r['seed']):r for r in [json.loads(x) for x in (root/(k+'-latency.jsonl')).read_text().splitlines()]} for k in ['27b','q2','q3']}
    review_path=root/'latency-text-review.json'
    latency_reviews={(r['label'],r['id'],r['seed']):r for r in json.loads(review_path.read_text())['grades']} if review_path.exists() else {}
    paired=[]
    for key in probes['27b'].keys() & probes['q3'].keys():
        if all(latency_reviews.get((r['label'],r['id'],r['seed']),{'text_pass':True})['text_pass'] and r['result']['finished'] and not any(x=='Unrequested action' for x in r['result']['unwanted_or_invalid_calls']) and (set(r['result']['done'])|set(r['result']['already_satisfied'])=={json.dumps(o,sort_keys=True,ensure_ascii=False) for o in cases[r['id']]['wanted']}) for r in [probes[k][key] for k in ['27b','q2','q3']]):paired.append(key)
    # These two fixed state-question answers are reviewed alongside the task rubrics.
    action_keys=[key for key in paired if all(probes[k][key]['result']['first_action_s'] is not None for k in ['27b','q2','q3'])]
    latency=dict(paired_correct_n=len(paired),paired_action_n=len(action_keys),excluded=[list(key) for key in probes['27b'] if key not in paired])
    for label in ['27b','q2','q3']:
        latency[label]=dict(completion_median_s=median(probes[label][key]['result']['elapsed_s'] for key in paired),first_action_median_s=median(probes[label][key]['result']['first_action_s'] for key in action_keys))
    summary['latency']=latency
for label in ['27b','q2','q3']:
    path=root/(label+'-capacity.jsonl')
    if path.exists():
        summary[label]['capacity_samples']=[{**{k:r[k] for k in ['length','rep']},'prompt_tokens':r['result']['prompt_tokens'],'output_tokens':r['result']['output_tokens'],'cached_tokens':r['result']['cached_tokens'],'ttft_s':r['result']['ttft_s'],'decode_tps':r['result']['output_tokens_per_decode_s'],'prefill_tps':(r['result'].get('timings') or {}).get('prompt_per_second')} for r in [json.loads(x) for x in path.read_text().splitlines()] if 'result' in r]
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
for k,v in summary.items():print(k,{x:y for x,y in v.items() if x!='outcomes'})
