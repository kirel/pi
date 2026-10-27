#!/usr/bin/env python3
"""Paired 4/6 expert-adaptation trial using the existing corpus and HA simulator."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import benchmark_ha_tool_quality as quality
import benchmark_update as previous
import benchmark_cache_01401 as cache

OUT = Path(__file__).parent / 'adapt-results-2026-10-18'
CORPUS = Path(__file__).parent / 'reasoning-results-2026-10-06/prefill-corpus.json'
MODEL, BASE = previous.MODEL, previous.BASE
CONFIG = cache.CONFIG[:cache.CONFIG.index("else:\n    c = json.loads")].replace('strata-cache-01401-benchmark-backup', 'strata-adapt-20261018-backup') + '''else:
    c = json.loads(backup.read_text())
    args = c['args']
    if '--adapt-every' in args:
        i = args.index('--adapt-every'); del args[i:i+2]
    args.extend(['--adapt-every', mode])
    cfg.write_text(json.dumps(c, indent=1) + '\\n')
'''
RUNTIME = cache.RUNTIME.replace("'--prompt-cache',", "'--adapt-every',")


def remote(argv, code=None):
    return cache.remote(cache.GPU_HOST, argv, code)


def ready():
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        try:
            d = previous.fetch('/v1/status')
            if d['engine'] == '0.1.45' and d['activity']['in_flight'] == 0:
                return d
        except Exception:
            pass
        time.sleep(3)
    raise RuntimeError('Readiness timeout')


def idle():
    assert previous.fetch('/v1/status')['activity']['in_flight'] == 0, 'External inference active'


def main():
    OUT.mkdir(exist_ok=False)
    corpus = json.loads(CORPUS.read_text())
    fixture_dir = Path(__file__).parent / 'ha-q3-results-2026-10-04'
    fixture = json.loads((fixture_dir/'cases.json').read_text())
    schemas = json.loads((fixture_dir/'ha-tools-live.json').read_text())['tools']
    tools = [{'type':'function','function':{'name':t['name'],'description':t.get('description',''),
              'parameters':t['inputSchema']}} for t in schemas]
    system = (fixture_dir/'system.txt').read_text()
    idle()
    (OUT/'method.json').write_text(json.dumps(dict(order=[4,6,6,4,4,6], lengths=[4096,65536],
        output_tokens=1024, reasoning='low', corpus_sha256=hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
        baseline=ready(), note='Fresh engine per block; identical 4K decode warmup. No OS cache flush.'),indent=2))
    remote(['sudo','python3','-','backup'], CONFIG)
    try:
        with (OUT/'observations.jsonl').open('x') as out:
            def save(row):
                out.write(json.dumps(row,ensure_ascii=False)+'\n');out.flush()
                print(json.dumps({k:v for k,v in row.items() if k not in ('result','runtime','native')},ensure_ascii=False),flush=True)
            for block, value in enumerate((4,6,6,4,4,6)):
                idle()
                remote(['sudo','python3','-',str(value)], CONFIG)
                remote(['docker','restart',MODEL]);ready()
                runtime=json.loads(remote(['docker','exec','-i',MODEL,'/opt/strata/.venv/bin/python','-'],RUNTIME))
                assert runtime['flags']['--adapt-every'] == str(value), runtime
                assert len(runtime['cuda_visible'].split(','))==2, runtime
                save(dict(kind='settings',block=block,value=value,runtime=runtime))
                for kind,length in [('warmup',4096)]+[('decode',n) for n in ((4096,65536) if block//2%2==0 else (65536,4096))]:
                    deadline=time.monotonic()+600
                    while True:
                        cards=previous.gpu()
                        if max(int(c['temperature_c']) for c in cards)<=70:break
                        if time.monotonic()>deadline:raise RuntimeError('Cooling timeout')
                        time.sleep(5)
                    idle();before=previous.fetch('/metrics')
                    case=next(c for c in corpus if c['length']==length)
                    case={**case,'seed':202610180000+length+(1000000 if kind=='warmup' else block//2)}
                    result=previous.speed.generate(BASE,MODEL,case,1024,'low')
                    after=previous.fetch('/metrics');native=previous.validate(before,after,result,False)
                    assert after['engine']['version']=='0.1.45'
                    save(dict(kind=kind,block=block,value=value,length=length,result=result,native=native,
                        decode_tok_s=native['decode_tok_s'],ttft_s=result['ttft_s'],elapsed_s=result['elapsed_s'],
                        gpu_before=cards,gpu_after=previous.gpu()))
                # Identical simulated action subset after speed samples, once per arm.
                if block in (0,1):
                    for case in fixture['cases']:
                        if case['id'] not in ('light-0','compound-2','other-0','noise-0','failure-0'):continue
                        idle();before=previous.fetch('/metrics')
                        result=quality.evaluate(BASE,MODEL,case,fixture,tools,system,20261018,'low',1024)
                        after=previous.fetch('/metrics')
                        assert after['totals']['requests']-before['totals']['requests']==result['rounds']
                        save(dict(kind='quality',block=block,value=value,case=case['id'],result=result,
                            passed=result['actions_pass'] and result['finished']))
                save(dict(kind='resources',block=block,value=value,
                    memory_events=remote(['docker','exec',MODEL,'cat','/sys/fs/cgroup/memory.events'])))
    finally:
        # A streaming failure may leave work in progress: allow it to finish before restart.
        ready()
        remote(['sudo','python3','-','restore'],CONFIG)
        remote(['docker','restart',MODEL]);ready()
        (OUT/'restored.json').write_text(json.dumps(dict(status=ready(),
            runtime=json.loads(remote(['docker','exec','-i',MODEL,'/opt/strata/.venv/bin/python','-'],RUNTIME))),indent=2))
        print('Original configuration restored.',flush=True)


if __name__=='__main__':main()
