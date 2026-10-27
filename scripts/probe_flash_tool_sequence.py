#!/usr/bin/env python3
"""Complete simulated multi-action loops; accept serial calls and extra reads."""
import argparse,json
from pathlib import Path
import time
from evaluate_flash_quality import equal, request


def operations(call):
    name,args=call['function']['name'],json.loads(call['function']['arguments'])
    if name=='set_light':
        if set(args)!={'entity_id','on'} or not isinstance(args['entity_id'],str) or type(args['on']) is not bool:
            raise ValueError('Invalid set_light arguments')
        return {json.dumps([name,args],sort_keys=True)}
    if name=='shopping_apply':
        if set(args)!={'complete_ids','delete_ids'} or not all(isinstance(args[k],list) and all(isinstance(i,str) for i in args[k]) for k in args):
            raise ValueError('Invalid shopping arguments')
        return {'complete:'+i for i in args['complete_ids']} | {'delete:'+i for i in args['delete_ids']}
    if name in ('get_home_state','shopping_snapshot') and args=={}:
        return set()
    raise ValueError('Unexpected function or arguments')


def shopping_state(done):
    return {'items':[{'id':i,'name':name,'completed':'complete:'+i in done}
                     for i,name in [('e17','Eier'),('m12','Milch'),('b03','Brot')]
                     if 'delete:'+i not in done]}


def probe(url,model,case,mode):
    wanted=set()
    for c in case['expected_calls']:
        wanted |= operations({'function':{'name':c['name'],'arguments':json.dumps(c['arguments'])}})
    messages=[{'role':'system','content':'Antworte auf Deutsch. Nutze die Test-Tools. Prüfe Ergebnisse; behauptete Änderungen müssen durch erfolgreiche Tool-Ergebnisse belegt sein.'},
              {'role':'user','content':case['prompt']+' Nach allen erfolgreichen Änderungen antworte nur mit {"completed":true}; wenn nicht alle erfolgreich waren, mit {"completed":false}.'}]
    greedy=mode=='greedy'
    payload=dict(model=model,messages=messages,tools=case['tools'],tool_choice='auto',max_tokens=384,
                 temperature=0 if greedy else 0.7,top_p=1 if greedy else 0.8,top_k=0 if greedy else 20,
                 presence_penalty=0 if greedy else 1.5,frequency_penalty=0,repetition_penalty=1,min_p=0,
                 seed=20261004,reasoning_effort='none',chat_template_kwargs={'enable_thinking':False})
    start=time.monotonic();done=set();unsafe=0;reads=0;replies=[];passed=False;errors=[];strict_json=None
    for _ in range(6):
        with request(url,'/v1/chat/completions',payload) as r: reply=json.load(r)
        replies.append(reply)
        choice=reply['choices'][0];m=choice['message'];calls=m.get('tool_calls') or []
        if not calls:
            content=m.get('content') or ''
            try:
                declared=equal(json.loads(content),{'completed':True});strict_json=True
            except ValueError:
                strict_json=False
                try: declared=equal(json.JSONDecoder().raw_decode(content[content.rfind('{'):])[0],{'completed':True})
                except ValueError: declared=False
            passed=done==wanted and unsafe==0 and declared and choice['finish_reason']=='stop'
            break
        messages.append({'role':'assistant','content':m.get('content'),'tool_calls':calls})
        for c in calls:
            try:
                ops=operations(c)
                if not ops <= wanted: raise ValueError('Unrequested mutation')
                changed=len(ops-done);done |= ops
                name=c['function']['name']
                result={'success':True,'changed':changed}
                if name=='shopping_snapshot':
                    result=shopping_state(done);reads+=1
                elif name=='get_home_state':
                    state={'light.wohnzimmer':False,'light.kueche':True}
                    for op in done:
                        if op.startswith('['):
                            _,args=json.loads(op);state[args['entity_id']]=args['on']
                    result={'lights':[{'entity_id':k,'on':v} for k,v in state.items()]};reads+=1
            except (ValueError,KeyError,TypeError) as exc:
                unsafe+=1;errors.append(str(exc));result={'success':False,'changed':0,'error':str(exc)}
            messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
    return dict(passed=passed,elapsed_s=time.monotonic()-start,rounds=len(replies),
                actions_complete=done==wanted,strict_json=strict_json,
                completed_operations=sorted(done),expected_operations=sorted(wanted),unsafe_calls=unsafe,
                extra_reads=reads,errors=errors,replies=replies)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ['url','model','label','cases','output']:p.add_argument('--'+arg,required=True)
    a=p.parse_args();cases=json.loads(Path(a.cases).read_text())['cases']
    if Path(a.output).exists():p.error('Retain existing results; choose another output path')
    with Path(a.output).open('w') as out:
        for case in [c for c in cases if c['id'] in ['two_lights','shopping_exact_ids']]:
            for mode in ['greedy','production']:
                result=probe(a.url,a.model,case,mode)
                out.write(json.dumps(dict(label=a.label,id=case['id'],mode=mode,result=result),ensure_ascii=False)+'\n');out.flush()
                print(case['id'],mode,result['passed'],result['rounds'],'rounds',result['extra_reads'],'extra reads',flush=True)
if __name__=='__main__':main()
