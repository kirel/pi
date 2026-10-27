#!/usr/bin/env python3
"""Mutating benchmark, restricted to uniquely named owned test tasks; cleanup in finally.

Run in hermes-local with LITELLM_API_KEY. Pass 'smoke' for one n8n correctness cycle.
Both variants use the same LiteLLM gateway. Only timings and synthetic IDs are logged.
"""
import json,os,pathlib,sys,time,uuid,statistics
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from benchmark_shopping_mcp import MCP,PROJECT

class Bench:
 def __init__(self):
  self.m=MCP('https://litellm.kirelabs.org/mcp/',os.environ['LITELLM_API_KEY'])
  self.run=uuid.uuid4().hex[:12];self.owned={};self.calls=0;self.bytes=0
  self.journal=pathlib.Path('/tmp/shopping-bench-owned-'+self.run+'.json')
  self.m.rpc('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'shopping-write-benchmark','version':'1'}})
 def call(self,name,args):
  self.calls+=1
  d,size=self.m.call(name,args);self.bytes+=size
  if isinstance(d,list):assert len(d)==1;d=d[0]
  return d
 def own(self,t):
  assert self.run in t['content'] and t['projectId']==PROJECT
  self.owned[t['id']]=t['content'];self.journal.write_text(json.dumps(self.owned))
 def tasks(self):
  tasks=[];args={'projectId':PROJECT,'responsibleUserFiltering':'all','limit':100};seen=set()
  while True:
   d=self.call('todoist-find-tasks',args);tasks+=d['tasks']
   if not d['hasMore']:return tasks
   cur=d.get('nextCursor');assert cur and cur not in seen;seen.add(cur);args['cursor']=cur
 def read(self,route,sections=True):
  if route=='n8n':
   d=self.call('shopping-shopping_snapshot',{});assert d['complete'];return d
  return {'tasks':self.tasks(),'sections':self.call('todoist-find-sections',{'projectId':PROJECT})['sections'] if sections else []}
 def apply(self,ops):
  d=self.call('shopping-shopping_apply',{'request_id':uuid.uuid4().hex,'operations':ops})
  if d.get('verified') is not True:
   print(json.dumps({'apply_failure':d}),flush=True)
  assert d.get('verified') is True
  for r in d['results']:
   if r.get('task') and self.run in r['task']['content']:self.own({**r['task'],'projectId':PROJECT})
  return d
 def fetch(self,expected):
  d=self.call('todoist-fetch',{'id':'task:'+expected['id']})
  assert d['title']==expected['content']
  meta=d.get('metadata',{})
  # Fetch metadata differs between releases. Fall back to full read exactly as the skill requires.
  expected_text=expected['content'] + ('\n\nDescription: '+expected['description'] if expected.get('description') else '')
  if not all(k in meta for k in ('projectId','sectionId')) or d['text']!=expected_text:
   got=next(t for t in self.tasks() if t['id']==expected['id'])
  else:got={**meta,'id':expected['id'],'content':d['title'],'description':expected.get('description','')}
  for k in ('content','description','projectId','sectionId'):assert (got.get(k) or '')==(expected.get(k) or ''),k
  return got
 def add(self,route,state,items,sec):
  if route=='n8n':
   d=self.apply([{'action':'add','content':name,'description':desc,'section':sec['name'],'expected_candidates':[t for t in state['tasks'] if t['content']==name]} for name,desc in items])
   return [{**r['task'],'projectId':PROJECT} for r in d['results']]
  d=self.call('todoist-add-tasks',{'tasks':[{'content':name,'description':desc,'projectId':PROJECT,'sectionId':sec['id']} for name,desc in items]})
  for t in d['tasks']:self.own(t)
  assert not d['failures'] and len(d['tasks'])==len(items)
  for t in d['tasks']:self.fetch(t)
  return d['tasks']
 def fingerprint(self):
  return sorted((t['id'],t['content'],t.get('description',''),t.get('sectionId')) for t in self.tasks() if '[MCP-BENCH ' not in t['content'])
 def cleanup(self):
  # Reconcile ambiguous creates by exact per-run marker before deleting owned IDs.
  for t in self.tasks():
   if '[MCP-BENCH '+self.run+' ' in t['content']:self.own(t)
  for tid in list(self.owned):
   d=self.call('todoist-delete-object',{'type':'task','id':tid});assert d['success']
   del self.owned[tid];self.journal.write_text(json.dumps(self.owned))
  assert not any('[MCP-BENCH '+self.run+' ' in t['content'] for t in self.tasks())
  self.journal.unlink(missing_ok=True);print(json.dumps({'cleanup':'verified','run':self.run}),flush=True)
 def cycle(self,route,cycle):
  prefix=f'[MCP-BENCH {self.run} {route}-{cycle}] '
  a=None;batch=None
  for scenario in ['add_one','already_present','refine','move','add_three','complete_two','merge_duplicates']:
   before=self.calls;size=self.bytes;start=time.perf_counter()
   state=self.read(route,scenario in ['add_one','already_present','move','add_three'])
   byid={t['id']:t for t in state['tasks']}
   if a and a['id'] in byid:a=byid[a['id']]
   if scenario=='add_one':
    sections=state['sections'];assert len(sections)>1
    sec=next((s for s in sections if s['name']=='Woanders'),sections[0]);other=next(s for s in sections if s['id']!=sec['id'])
    a=self.add(route,state,[(prefix+'Pesto','vegan')],sec)[0]
   elif scenario=='already_present':
    assert a['content']==prefix+'Pesto' and a['description']=='vegan'
   elif scenario=='refine':
    expected={**a,'description':'vegan, Marke Test'}
    if route=='n8n':self.apply([{'action':'update','id':a['id'],'expected':a,'description':expected['description']}])
    else:
     d=self.call('todoist-update-tasks',{'tasks':[{'id':a['id'],'description':expected['description']}]});assert not d['failures'];self.fetch(expected)
   elif scenario=='move':
    expected={**a,'sectionId':other['id']}
    if route=='n8n':self.apply([{'action':'move','id':a['id'],'expected':a,'section':other['name']}])
    else:
     d=self.call('todoist-update-tasks',{'tasks':[{'id':a['id'],'sectionId':other['id']}]});assert not d['failures'];self.fetch(expected)
   elif scenario=='add_three':batch=self.add(route,state,[(prefix+'Milch','Hafer'),(prefix+'Milch','ungesüßt'),(prefix+'Brot','Vollkorn')],sec)
   elif scenario=='complete_two':
    selected=[byid[a['id']],byid[batch[2]['id']]]
    if route=='n8n':self.apply([{'action':'complete','id':t['id'],'expected':t} for t in selected])
    else:
     d=self.call('todoist-complete-tasks',{'ids':[t['id'] for t in selected]});assert not d['failures']
     remaining={t['id'] for t in self.tasks()};assert not remaining.intersection(t['id'] for t in selected)
   else:
    keep,drop=[byid[t['id']] for t in batch[:2]]
    if route=='n8n':self.apply([{'action':'merge','id':keep['id'],'expected':keep,'duplicates':[{'id':drop['id'],'expected':drop}]}])
    else:
     description=keep['description']+'\n'+drop['description']
     d=self.call('todoist-update-tasks',{'tasks':[{'id':keep['id'],'description':description}]});assert not d['failures'];self.fetch({**keep,'description':description})
     d=self.call('todoist-complete-tasks',{'ids':[drop['id']]});assert not d['failures']
     remaining={t['id']:t for t in self.tasks()};assert drop['id'] not in remaining and remaining[keep['id']]['description']==description
   print(json.dumps({'route':route,'cycle':cycle,'scenario':scenario,'seconds':time.perf_counter()-start,'tool_calls':self.calls-before,'response_json_bytes':self.bytes-size,'verified':True}),flush=True)

def main():
 b=Bench();original=b.fingerprint()
 try:
  if 'smoke' in sys.argv:b.cycle('n8n',0)
  else:
   for cycle in range(3):
    for route in (['n8n','official'] if cycle%2==0 else ['official','n8n']):b.cycle(route,cycle)
 finally:
  b.cleanup()
  assert b.fingerprint()==original,'Non-benchmark task state changed during run'
  print(json.dumps({'non_benchmark_tasks_unchanged':True}),flush=True)
def self_check():
 b=Bench.__new__(Bench)
 expected={'id':'1','content':'Test','description':'Detail A\nDetail B','projectId':PROJECT,'sectionId':'s'}
 response={'title':'Test','text':'Test\n\nDescription: Detail A\nDetail B','metadata':{'projectId':PROJECT,'sectionId':'s'}}
 b.call=lambda *args:response
 def unexpected_read():raise AssertionError('Description in Fetch text must not trigger another list read')
 b.tasks=unexpected_read
 assert b.fetch(expected)==expected
 del response['metadata']['sectionId']
 used=[]
 def fallback():used.append(True);return [expected]
 b.tasks=fallback
 assert b.fetch(expected)==expected and len(used)==1
 print('benchmark Fetch verification: text and fallback checks passed')
if __name__=='__main__':
 if '--self-check' in sys.argv:self_check()
 else:main()
