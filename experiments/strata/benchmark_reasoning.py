#!/usr/bin/env python3
"""Compare none/low on existing Strata profiles; HA actions are simulated only."""
import argparse
import json
from pathlib import Path
import subprocess
import time

import benchmark_flash_prefill as speed
import benchmark_ha_tool_quality as quality


MODELS = {'q3': 'Qwen3.8-Flash-Next-IQ3_XXS-Strata',
          'q2': 'Qwen3.8-Flash-Next-IQ2_XS-Strata'}
BASE = 'http://127.0.0.1:9292'


def fetch(url, path):
    with speed.request(url, path) as response:
        return json.load(response)


def load(model):
    with speed.request(BASE, '/v1/chat/completions', dict(
        model=model, messages=[{'role': 'user', 'content': 'What is 19+23? Answer only 42.'}],
        reasoning_effort='none', chat_template_kwargs={'enable_thinking': False},
        temperature=0, max_tokens=32)) as response:
        result=json.load(response)
        assert result['choices'][0]['message']['content'].strip() == '42', result


def snapshot(model):
    inspected = json.loads(subprocess.check_output(['docker', 'inspect', model]))[0]
    return dict(at=time.time(), status=fetch(BASE+'/upstream/'+model, '/v1/status'),
                metrics=fetch(BASE+'/upstream/'+model, '/metrics'),
                image=inspected['Config']['Image'], state=inspected['State'],
                memory_limit=inspected['HostConfig']['Memory'],
                devices=inspected['HostConfig']['DeviceRequests'],
                gpu=subprocess.check_output(['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total,utilization.gpu',
                                             '--format=csv,noheader'], text=True),
                memory=subprocess.check_output(['free', '-m'], text=True),
                cgroup=subprocess.check_output(['docker','exec',model,'cat','/sys/fs/cgroup/memory.events'],text=True))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fixtures',type=Path,required=True)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--stage',choices=['all','quality','speed','latency'],default='all')
    p.add_argument('--latency-seed',type=int,default=20261006)
    p.add_argument('--speed-lengths',default='4096,16384,65536,128000')
    p.add_argument('--speed-repetitions',type=int,default=3)
    p.add_argument('--decode-lengths',default='4096,65536,128000')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    fixture=json.loads((a.fixtures/'cases.json').read_text())
    schemas=json.loads((a.fixtures/'ha-tools-live.json').read_text())['tools']
    tools=[{'type':'function','function':{'name':t['name'],'description':t.get('description',''),
                                        'parameters':t['inputSchema']}} for t in schemas]
    system=(a.fixtures/'system.txt').read_text()
    corpus=json.loads(a.corpus.read_text())
    sources={length:next(c for c in corpus if c['length']==length) for length in [4096,16384,65536,128000]}
    running=fetch(BASE,'/running')['running']
    original=next(r['model'] for r in running if r['model'] in MODELS.values())
    (a.output/('original-'+a.stage+'.json')).write_text(json.dumps({'at':time.time(),'model':original,
                                                    'running':[r['model'] for r in running]},indent=2))
    try:
        for quant,model in MODELS.items():
            if a.stage=='quality' and all((f:=a.output/(quant+'-'+e+'-ha.jsonl')).exists() and len(f.read_text().splitlines())==2*len(fixture['cases']) for e in ['none','low']):
                continue
            print('LOAD',quant,flush=True);load(model)
            url=BASE+'/upstream/'+model
            (a.output/(quant+'-before-'+a.stage+'.json')).write_text(json.dumps(snapshot(model),indent=2))
            if a.stage in ['all','speed']:
                handles={effort:(a.output/(quant+'-'+effort+'-speed.jsonl')).open('a') for effort in ['none','low']}
                seen={e:{(r['kind'],r['length'],r['rep']) for l in (a.output/(quant+'-'+e+'-speed.jsonl')).read_text().splitlines() if (r:=json.loads(l))} for e in handles}
                try:
                    def measure(effort,case,kind,decode=0,allow_cache=False):
                        if kind not in ['warmup','warm-prime'] and (kind,case['length'],case.get('rep',0)) in seen[effort]:
                            return
                        result=speed.generate(url,model,case,decode,effort,allow_cache)
                        row=dict(label=quant+'-'+effort,kind=kind,length=case['length'],rep=case.get('rep',0),result=result)
                        handles[effort].write(json.dumps(row,ensure_ascii=False)+'\n');handles[effort].flush()
                        print(row['label'],kind,case['length'],round(result['ttft_s'],3),
                              round(result['first_visible_s'] or 0,3),'cached',result['cached_tokens'],flush=True)
                    for effort in ['none','low']:
                        measure(effort,dict(length=0,seed=time.time_ns(),text='Warmup.'),'warmup')
                        measure(effort,{**sources[65536],'seed':time.time_ns()},'warmup')
                    order=0
                    for length in map(int,a.speed_lengths.split(',')):
                        source=sources[length]
                        for rep in range(1 if length==128000 else a.speed_repetitions):
                            for effort in (['none','low'] if order%2==0 else ['low','none']):
                                measure(effort,{**source,'rep':rep,'seed':time.time_ns()},'cold')
                            order+=1
                    for i,length in enumerate(map(int,a.decode_lengths.split(','))):
                        for effort in (['none','low'] if i%2==0 else ['low','none']):
                            measure(effort,{**sources[length],'seed':time.time_ns()},'decode',1024)
                    for effort in ['none','low']:
                        warm={**sources[16384],'seed':time.time_ns()}
                        measure(effort,warm,'warm-prime')
                        for rep in range(3):measure(effort,{**warm,'rep':rep},'warm',allow_cache=True)
                finally:
                    for out in handles.values():out.close()
            if a.stage in ['all','quality']:
                # Counterbalance effort order across seeds while keeping each simulated state fresh.
                handles={effort:(a.output/(quant+'-'+effort+'-ha.jsonl')).open('x') for effort in ['none','low']}
                try:
                    for seed in [20261004,20261005]:
                        for effort in (['none','low'] if seed==20261004 else ['low','none']):
                            for case in fixture['cases']:
                                result=quality.evaluate(url,model,case,fixture,tools,system,seed,effort,2048)
                                row=dict(label=quant+'-'+effort,id=case['id'],category=case['category'],
                                         seed=seed,rubric=case['rubric'],result=result)
                                handles[effort].write(json.dumps(row,ensure_ascii=False)+'\n');handles[effort].flush()
                                print('HA',row['label'],case['id'],seed,result['actions_pass'],
                                      result['rounds'],round(result['elapsed_s'],2),flush=True)
                finally:
                    for out in handles.values():out.close()
            if a.stage=='latency':
                ids=['light-0','light-1','light-2','light-3','light-4','light-5',
                     'compound-0','compound-2','compound-6','state-1','state-7','followup-brighter']
                order=['none','low'] if quant=='q3' else ['low','none']
                if a.latency_seed % 2:order.reverse()
                for effort in order:
                    # Prime the mode; the following varying requests must prove prefix reuse.
                    prime=quality.evaluate(url,model,fixture['cases'][0],fixture,tools,system,a.latency_seed,effort,2048)
                    (a.output/(quant+'-'+effort+'-latency-prime-'+str(a.latency_seed)+'.json')).write_text(json.dumps(prime,indent=2))
                    path=a.output/(quant+'-'+effort+'-latency.jsonl')
                    seen={(r['id'],r['seed']) for line in path.read_text().splitlines() if (r:=json.loads(line))} if path.exists() else set()
                    with path.open('a') as out:
                        for case in [c for c in fixture['cases'] if c['id'] in ids]:
                            if (case['id'],a.latency_seed) in seen:continue
                            result=quality.evaluate(url,model,case,fixture,tools,system,a.latency_seed,effort,2048)
                            row=dict(label=quant+'-'+effort,id=case['id'],category=case['category'],
                                     seed=a.latency_seed,rubric=case['rubric'],result=result)
                            out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
                            print('LATENCY',row['label'],case['id'],result['actions_pass'],round(result['elapsed_s'],2),flush=True)
            (a.output/(quant+'-after-'+a.stage+'.json')).write_text(json.dumps(snapshot(model),indent=2))
    finally:
        print('RESTORE',original,flush=True);load(original)
        (a.output/('restored-'+a.stage+'.json')).write_text(json.dumps(snapshot(original),indent=2))


if __name__=='__main__':
    main()
