#!/usr/bin/env python3
"""Combine recorded action evidence with explicit text reviews."""
import json
import math
from pathlib import Path
from statistics import median
import sys


def extra_side_effects(result):
    # These offered mutations are never requested by this fixture. The simulator
    # rejects them as unsupported, but their attempted effects still matter.
    names={'assist_satellite__HassBroadcast','intent__HassCancelAllTimers','fan__HassFanSetSpeed'}
    return [call['function']['name'] for reply in result['replies']
            for call in reply['choices'][0]['message'].get('tool_calls',[])
            if call['function']['name'] in names]


def summarize(root,suffix='ha'):
    fixture=json.loads((root/'cases.json').read_text())
    cases={c['id']:c for c in fixture['cases']}
    reviews={(r['label'],r['id'],r['seed']):r for r in json.loads((root/'text-reviews.json').read_text())['grades']}
    summary={}
    for label in ['q3-none','q3-low','q2-none','q2-low']:
        if not (root/(label+'-'+suffix+'.jsonl')).exists():
            continue
        rows=[json.loads(l) for l in (root/(label+'-'+suffix+'.jsonl')).read_text().splitlines()]
        outcomes=[]
        for r in rows:
            c=cases[r['id']];z=r['result'];bad=z['unwanted_or_invalid_calls']
            wanted={json.dumps(o,sort_keys=True,ensure_ascii=False) for o in c['wanted']}
            failed={json.dumps(c['fail_target'],sort_keys=True,ensure_ascii=False)} if 'fail_target' in c else set()
            complete=set(z['done'])|set(z['already_satisfied'])==wanted-failed and failed<=set(z['attempted'])
            no_tools_ok=not c.get('no_tools') or len(z['replies'])==1 and not z['replies'][0]['choices'][0]['message'].get('tool_calls')
            review=reviews[(label,r['id'],r['seed'])]
            text=review['text_pass']
            extra=extra_side_effects(z)
            substantive=complete and 'Unrequested action' not in bad and not extra and no_tools_ok and z['finished']
            outcomes.append(dict(id=r['id'],seed=r['seed'],category=r['category'],
                                 passed=substantive and text,
                                 semantic_passed=substantive and (text or review.get('style_only',False)),
                                 style_only=review.get('style_only',False),
                                 text_pass=text,actions_complete=complete,unwanted_calls=bad.count('Unrequested action')+len(extra),
                                 unsupported_side_effects=extra,
                                 invalid_calls=sum(e not in ['Unrequested action','No matching device'] for e in bad),
                                 elapsed_s=z['elapsed_s'],first_action_s=z['first_action_s'],
                                 truncated=any(x['choices'][0]['finish_reason']=='length' for x in z['replies']),
                                 reasoning_chars=z['reasoning_chars']))
        path=root/(label+'-speed.jsonl')
        speeds=[json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []
        summary[label]=dict(total=len(outcomes),passed=sum(o['passed'] for o in outcomes),
                            semantic_passed=sum(o['semantic_passed'] for o in outcomes),
                            style_failures=sum(o['style_only'] for o in outcomes),
                            unwanted_observations=sum(o['unwanted_calls']>0 for o in outcomes),
                            unwanted_calls=sum(o['unwanted_calls'] for o in outcomes),
                            invalid_calls=sum(o['invalid_calls'] for o in outcomes),
                            truncated_observations=sum(o['truncated'] for o in outcomes),
                            median_completion_s=median(o['elapsed_s'] for o in outcomes),
                            categories={cat:dict(total=sum(o['category']==cat for o in outcomes),
                                                 passed=sum(o['category']==cat and o['passed'] for o in outcomes),
                                                 semantic_passed=sum(o['category']==cat and o['semantic_passed'] for o in outcomes))
                                        for cat in sorted({o['category'] for o in outcomes})},
                            speed={kind:{str(length):dict(n=len(group),
                                        ttft_s=median(r['result']['ttft_s'] for r in group),
                                        first_visible_s=median(r['result']['first_visible_s'] for r in group),
                                        elapsed_s=median(r['result']['elapsed_s'] for r in group),
                                        decode_tps=median(r['result']['output_tokens_per_decode_s'] for r in group),
                                        native_prefill_tps=median(r['result']['timings']['prompt_per_second'] for r in group),
                                        cached_tokens=[r['result']['cached_tokens'] for r in group])
                                        for length in sorted({r['length'] for r in speeds if r['kind']==kind})
                                        if (group:=[r for r in speeds if r['kind']==kind and r['length']==length])}
                                   for kind in ['cold','decode','warm']},outcomes=outcomes)
    summary['paired']={}
    for quant in ['q3','q2']:
        if not all(quant+'-'+e in summary for e in ['none','low']):
            continue
        by_effort={e:{(o['id'],o['seed']):o for o in summary[quant+'-'+e]['outcomes']} for e in ['none','low']}
        keys=by_effort['none'].keys() & by_effort['low'].keys()
        correct=[k for k in keys if all(by_effort[e][k]['semantic_passed'] for e in ['none','low'])]
        actions=[k for k in correct if all(by_effort[e][k]['first_action_s'] is not None for e in ['none','low'])]
        summary['paired'][quant]=dict(correct_n=len(correct),action_n=len(actions),
            low_only_pass=sum(not by_effort['none'][k]['passed'] and by_effort['low'][k]['passed'] for k in keys),
            none_only_pass=sum(by_effort['none'][k]['passed'] and not by_effort['low'][k]['passed'] for k in keys),
            semantic_low_only_pass=sum(not by_effort['none'][k]['semantic_passed'] and by_effort['low'][k]['semantic_passed'] for k in keys),
            semantic_none_only_pass=sum(by_effort['none'][k]['semantic_passed'] and not by_effort['low'][k]['semantic_passed'] for k in keys),
            completion_extra_median_s=median(by_effort['low'][k]['elapsed_s']-by_effort['none'][k]['elapsed_s'] for k in correct),
            completion_extra_p95_s=sorted(by_effort['low'][k]['elapsed_s']-by_effort['none'][k]['elapsed_s'] for k in correct)[math.ceil(len(correct)*.95)-1],
            action_extra_median_s=median(by_effort['low'][k]['first_action_s']-by_effort['none'][k]['first_action_s'] for k in actions),
            action_extra_p95_s=sorted(by_effort['low'][k]['first_action_s']-by_effort['none'][k]['first_action_s'] for k in actions)[math.ceil(len(actions)*.95)-1],
            latency={e:dict(completion_s=median(by_effort[e][k]['elapsed_s'] for k in correct),
                            completion_p95_s=sorted(by_effort[e][k]['elapsed_s'] for k in correct)[math.ceil(len(correct)*.95)-1],
                            first_action_s=median(by_effort[e][k]['first_action_s'] for k in actions),
                            first_action_p95_s=sorted(by_effort[e][k]['first_action_s'] for k in actions)[math.ceil(len(actions)*.95)-1]) for e in ['none','low']})
    return summary


if __name__=='__main__':
    root=Path(sys.argv[1]);suffix=sys.argv[2] if len(sys.argv)>2 else 'ha';result=summarize(root,suffix)
    (root/('warm-summary.json' if suffix=='latency' else 'summary.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    for label,value in result.items():
        print(label,json.dumps({k:v for k,v in value.items() if k!='outcomes'},ensure_ascii=False))
