#!/usr/bin/env python3
"""Live isolated safety checks; uses only uniquely marked owned test tasks."""
import concurrent.futures,uuid,json
from benchmark import Bench
b=Bench();original=b.fingerprint()
try:
 s=b.read('n8n');sec=next((x for x in s['sections'] if x['name']=='Woanders'),s['sections'][0])
 op={'action':'add','content':f'[MCP-BENCH {b.run} safety] Pesto','description':'vegan','section':sec['name'],'expected_candidates':[]}
 rid=uuid.uuid4().hex
 first=b.call('shopping-shopping_apply',{'request_id':rid,'operations':[op]});assert first['verified']
 task={**first['results'][0]['task'],'projectId':s['projectId']};b.own(task)
 repeat=b.call('shopping-shopping_apply',{'request_id':rid,'operations':[op]});assert repeat['status']=='conflict'
 noop=b.call('shopping-shopping_apply',{'request_id':uuid.uuid4().hex,'operations':[{**op,'expected_candidates':[task]}]})
 assert noop['results'][0]['status']=='already_present'
 stale=b.call('shopping-shopping_apply',{'request_id':uuid.uuid4().hex,'operations':[{'action':'update','id':task['id'],'expected':{**task,'description':'wrong old value'},'description':'must not be written'}]})
 assert stale['status']=='conflict'
 current=next(t for t in b.read('n8n')['tasks'] if t['id']==task['id']);assert current['description']=='vegan'
 b.apply([{'action':'complete','id':task['id'],'expected':current}])
 replay=b.call('shopping-shopping_apply',{'request_id':rid,'operations':[op]})
 assert replay['verified'] is False and replay['results'][0]['status']=='uncertain'
 assert not any(t['content']==op['content'] for t in b.read('n8n')['tasks'])
 race={**op,'content':op['content']+' parallel'}
 def add():return b.call('shopping-shopping_apply',{'request_id':uuid.uuid4().hex,'operations':[race]})
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  futures=[pool.submit(add),pool.submit(add)];results=[f.result() for f in futures]
 assert sum(r.get('verified') is True for r in results)==1
 assert any(r.get('status') in ('busy','conflict') for r in results)
 matches=[t for t in b.read('n8n')['tasks'] if t['content']==race['content']];assert len(matches)==1;b.own(matches[0])
 current=b.read('n8n')
 pair=b.add('n8n',current,[(f'[MCP-BENCH {b.run} mixed] Milch','Detail A'),(f'[MCP-BENCH {b.run} mixed] Milch','Detail B')],sec)
 mixed=b.apply([{'action':'add','content':f'[MCP-BENCH {b.run} mixed] Brot','description':'Test','section':sec['name'],'expected_candidates':[]},{'action':'merge','id':pair[0]['id'],'expected':pair[0],'duplicates':[{'id':pair[1]['id'],'expected':pair[1]}]}])
 assert mixed['verified'] and len(mixed['results'])==2
 print(json.dumps({'replay_no_duplicate':True,'already_present_no_write':True,'stale_plan_rejected':True,'sync_uuid_replay_after_completion_no_recreation':True,'concurrent_add_exactly_one':True,'mixed_add_and_merge_verified':True}),flush=True)
finally:
 b.cleanup();assert original==b.fingerprint()
 print(json.dumps({'non_benchmark_tasks_unchanged':True}),flush=True)
