#!/usr/bin/env python3
"""Summarize paired adaptation trials; retain thermal caveats and individual pairs."""
import json
from pathlib import Path
from statistics import median


def summarize(rows):
    result={}
    for length in (4096,65536):
        samples=[r for r in rows if r['kind']=='decode' and r['length']==length]
        arms={v:[r for r in samples if r['value']==v] for v in (4,6)}
        assert all(len(x)==3 for x in arms.values()), 'Expected three samples per arm'
        metrics={}
        for key in ('decode_tok_s','ttft_s','elapsed_s'):
            a,b=(median(r[key] for r in arms[v]) for v in (4,6))
            metrics[key]={'4':a,'6':b,'change_percent':100*(b/a-1)}
        pairs=[]
        for p in range(3):
            pair={r['value']:r for r in samples if r['block']//2==p}
            pairs.append(100*(pair[6]['decode_tok_s']/pair[4]['decode_tok_s']-1))
        result[str(length)]={'metrics':metrics,'paired_decode_changes_percent':pairs,
            'thermal_after_samples':sum(any(g['thermal']=='Active' for g in r['gpu_after']) for r in samples)}
    result['quality']={str(v):[{'case':r['case'],'passed':r['passed']} for r in rows
        if r['kind']=='quality' and r['value']==v] for v in (4,6)}
    return result


if __name__=='__main__':
    root=Path(__file__).parent/'adapt-results-2026-10-18'
    result=summarize([json.loads(l) for l in (root/'observations.jsonl').read_text().splitlines()])
    (root/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
