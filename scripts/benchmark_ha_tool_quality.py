#!/usr/bin/env python3
"""Stateful HA-like dialogue test using captured live schemas and simulated devices."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
from evaluate_flash_quality import request


def validate(value, schema):
    if 'anyOf' in schema:
        for choice in schema['anyOf']:
            try:
                validate(value, choice)
                return
            except ValueError:
                pass
        raise ValueError('No matching schema type')
    types={'object':dict,'array':list,'string':str,'integer':int,'boolean':bool}
    typ=schema.get('type')
    if typ in types and type(value) is not types[typ]:
        raise ValueError('Wrong argument type')
    if 'enum' in schema and value not in schema['enum']:
        raise ValueError('Invalid enum')
    if typ=='object':
        properties=schema.get('properties',{})
        if set(value)-properties.keys() or set(schema.get('required',[]))-value.keys():
            raise ValueError('Unknown or missing argument')
        for key,item in value.items(): validate(item,properties[key])
    if typ=='array':
        for item in value: validate(item,schema.get('items',{}))
    if typ=='integer' and not schema.get('minimum',value)<=value<=schema.get('maximum',value):
        raise ValueError('Out of range')


def operation(name,area,kind,value):
    return json.dumps(dict(name=name,area=area,kind=kind,value=value),sort_keys=True,ensure_ascii=False)


def selected(entities,args):
    name=args.get('name','').strip().casefold()
    domains=args.get('domain') or []
    if isinstance(domains,str):domains=[domains]
    domains=[d.strip().lower() for d in domains]
    return [e for e in entities if
            (not name or name=='all' or name in [e.get('entity_id','').casefold()]+[n.strip().casefold() for n in e.get('aliases',[e['name']])]) and
            ('area' not in args or e['area'].casefold()==args['area'].strip().casefold()) and
            (not domains or e['domain'] in domains) and
            (not args.get('device_class') or e.get('device_class') in args['device_class']) and
            ('floor' not in args or e.get('floor')==args['floor'])]


def live_context(entities):
    infos=[]
    for e in entities:
        info=dict(names=', '.join(e.get('aliases',[e['name']])),domain=e['domain'],areas=e['area'],state=e['state'])
        attrs={k:e[k] for k in ['device_class','temperature'] if k in e}
        if 'brightness' in e:attrs['brightness']=str(round(e['brightness']*255/100))
        if 'volume_level' in e:attrs['volume_level']=e['volume_level']/100
        if 'position' in e:attrs['current_position']=str(e['position'])
        if 'unit' in e:attrs['unit_of_measurement']=e['unit']
        if attrs:info['attributes']=attrs
        infos.append(info)
    return {'success':True,'result':'Live Context: An overview of the areas and the devices in this smart home:\n'+json.dumps(infos,ensure_ascii=False)}


def simulate(name,args,entities):
    if name=='homeassistant__GetLiveContext':
        targets=selected(entities,args)
        return set(), live_context(targets) if targets else {'success':False,'error':'No exposed entities matched the filters'}
    if name.startswith('script__'):
        return {operation(name,'*','script',True)}, {'success':True}
    domains={'light__HassLightSet':'light','intent__HassSetPosition':'cover',
             'media_player__HassSetVolume':'media_player','media_player__HassMediaPause':'media_player',
             'media_player__HassMediaUnpause':'media_player'}
    if name not in domains and name not in ('intent__HassTurnOn','intent__HassTurnOff'):
        raise ValueError('Unsupported action in this fixture')
    targets=selected(entities,args)
    if name in domains: targets=[e for e in targets if e['domain']==domains[name]]
    if not targets: return set(), {'success':False,'error':'No matching device'}
    if 'name' in args and 'area' not in args and len(targets)>1:
        return set(), {'success':False,'error':'Ambiguous device; specify the area'}
    ops=set()
    for e in targets:
        if name in ('intent__HassTurnOn','intent__HassTurnOff'):
            if e['domain']=='light': kind,value='on',name.endswith('TurnOn')
            elif e['domain']=='cover': kind,value='position',100 if name.endswith('TurnOn') else 0
            else: raise ValueError('Unsupported target domain')
        elif name=='light__HassLightSet':
            if set(args)&{'color','temperature'} or 'brightness' not in args: raise ValueError('Unexpected light setting')
            kind,value='brightness',args['brightness']
        elif name=='intent__HassSetPosition': kind,value='position',args['position']
        elif name=='media_player__HassSetVolume': kind,value='volume_level',args['volume_level']
        else: kind,value='state','paused' if name.endswith('Pause') else 'playing'
        ops.add(operation(e['name'],e['area'],kind,value))
    return ops, {'success':True}


def semantic_ops(ops,wanted):
    """Accept light brightness zero as off, and positive brightness as on."""
    out=set()
    for op in ops:
        o=json.loads(op)
        equivalent=operation(o['name'],o['area'],'on',o['value']>0) if o['kind']=='brightness' else op
        out.add(equivalent if equivalent in wanted else op)
    return out


def apply(entities,ops):
    for op in ops:
        o=json.loads(op)
        for e in entities:
            if e['name']==o['name'] and e['area']==o['area']:
                if o['kind']=='on':
                    e['state']='on' if o['value'] else 'off'
                    if o['value'] and not e.get('brightness'):e['brightness']=100
                else:
                    e[o['kind']]=o['value']
                    if o['kind']=='brightness':e['state']='on' if o['value'] else 'off'
                    if o['kind']=='position':e['state']='closed' if o['value']==0 else 'open'


def evaluate(url,model,case,fixture,tools,system,seed,reasoning_effort='none',max_tokens=384):
    messages=[{'role':'system','content':system}]+copy.deepcopy(case.get('history',[]))+[{'role':'user','content':case['prompt']}]
    payload=dict(model=model,messages=messages,tools=tools,tool_choice='auto',max_tokens=max_tokens,
                 temperature=0.7,top_p=0.8,top_k=20,min_p=0,presence_penalty=1.5,
                 frequency_penalty=0,repetition_penalty=1,seed=seed,reasoning_effort=reasoning_effort,
                 chat_template_kwargs={'enable_thinking':reasoning_effort!='none'},cache_prompt=False)
    schemas={t['function']['name']:t['function']['parameters'] for t in tools}
    wanted={json.dumps(o,sort_keys=True,ensure_ascii=False) for o in case['wanted']}
    failed={json.dumps(case['fail_target'],sort_keys=True,ensure_ascii=False)} if 'fail_target' in case else set()
    entities=copy.deepcopy(fixture['entities']);done=set();attempted=set();bad=[];replies=[];reads=0
    already=set()
    for op in wanted-failed:
        o=json.loads(op)
        for e in entities:
            if e['name']==o['name'] and e['area']==o['area'] and (e['state']=='on' if o['kind']=='on' else e.get(o['kind']))==o['value']:
                already.add(op)
    start=time.monotonic();first_action=None;first_reply=None;content='';finished=False
    try:
        # ponytail: at most six model turns; longer workflows need a separate agent benchmark.
        for _ in range(6):
            with request(url,'/v1/chat/completions',payload) as r: reply=json.load(r)
            now=time.monotonic()-start
            if first_reply is None:first_reply=now
            replies.append(reply);choice=reply['choices'][0];m=choice['message'];calls=m.get('tool_calls') or []
            if not calls:
                content=m.get('content') or '';finished=choice['finish_reason']=='stop';break
            messages.append({'role':'assistant','content':m.get('content'),'tool_calls':calls})
            for c in calls:
                try:
                    name=c['function']['name'];args=json.loads(c['function']['arguments'])
                    validate(args,schemas[name]);ops,result=simulate(name,args,entities)
                    if name=='homeassistant__GetLiveContext':reads+=1
                    elif ops:
                        if first_action is None:first_action=time.monotonic()-start
                        actual_ops=ops;ops=semantic_ops(ops,wanted)
                        attempted |= ops
                        if not ops<=wanted:raise ValueError('Unrequested action')
                        if ops & failed:
                            result={'success':False,'error':'Device not reachable; no action performed.'}
                        else:
                            apply(entities,actual_ops);done |= ops
                    if case.get('no_tools'):raise ValueError('No tool allowed for noise')
                except (ValueError,KeyError,TypeError) as exc:
                    bad.append(str(exc));result={'success':False,'error':str(exc)}
                messages.append({'role':'tool','tool_call_id':c['id'],'content':json.dumps(result,ensure_ascii=False)})
    except Exception as exc:
        bad.append(type(exc).__name__+': '+str(exc))
    return dict(reasoning_effort=reasoning_effort,max_tokens=max_tokens,
                reasoning_chars=sum(len(r['choices'][0]['message'].get('reasoning_content') or '') for r in replies),
                actions_pass=done|already==wanted-failed and failed<=attempted and not bad,
                finished=finished,final_text=content,elapsed_s=time.monotonic()-start,
                first_reply_s=first_reply,first_action_s=first_action,reads=reads,rounds=len(replies),
                unwanted_or_invalid_calls=bad,done=sorted(done),already_satisfied=sorted(already),attempted=sorted(attempted),replies=replies,
                prompt_sha256=hashlib.sha256(json.dumps(payload['messages'][:1]+case.get('history',[])+[{'role':'user','content':case['prompt']}],ensure_ascii=False).encode()).hexdigest())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['url','model','label','fixtures','schemas','system','output']:p.add_argument('--'+key,required=True)
    p.add_argument('--seeds',nargs='+',type=int,default=[20261004])
    p.add_argument('--reasoning-effort',choices=['none','low'],default='none')
    p.add_argument('--max-tokens',type=int,default=384)
    a=p.parse_args();fixture=json.loads(Path(a.fixtures).read_text())
    tools=[{'type':'function','function':{'name':t['name'],'description':t.get('description',''),'parameters':t['inputSchema']}} for t in json.loads(Path(a.schemas).read_text())['tools']]
    system=Path(a.system).read_text()
    with Path(a.output).open('x') as out:
        for seed in a.seeds:
            for case in fixture['cases']:
                result=evaluate(a.url,a.model,case,fixture,tools,system,seed,a.reasoning_effort,a.max_tokens)
                out.write(json.dumps(dict(label=a.label,id=case['id'],category=case['category'],seed=seed,rubric=case['rubric'],result=result),ensure_ascii=False)+'\n');out.flush()
                print(case['id'],seed,result['actions_pass'],result['rounds'],round(result['elapsed_s'],2),flush=True)
if __name__=='__main__':main()
