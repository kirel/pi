#!/usr/bin/env python3
"""Publish shopping workflows through the existing Codex n8n MCP connection."""
import json,pathlib,sys,uuid,shlex,time,tomllib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[2]
cfg=tomllib.loads((pathlib.Path.home()/'.codex/config.toml').read_text())['mcp_servers']['litellm']
def call(name,args):
 headers={**cfg['http_headers'],'Content-Type':'application/json','Accept':'application/json, text/event-stream'}
 req=urllib.request.Request(cfg['url'],data=json.dumps({'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'n8n-'+name,'arguments':args}}).encode(),headers=headers)
 with urllib.request.urlopen(req,timeout=120) as r: raw=r.read().decode()
 events=[json.loads(x[5:]) for x in raw.splitlines() if x.startswith('data:')]
 r=next((x for x in events if x.get('id')==1),None) or json.loads(raw)
 d=json.loads(r['result']['content'][0]['text'])
 if d.get('success') is False:raise RuntimeError(str(d))
 return d

def node(name,typ,version,params,**extra):
 return dict(id=str(uuid.uuid4()),name=name,type=typ,typeVersion=version,parameters=params,position=[0,0],**extra)
def code(name,js):return node(name,'n8n-nodes-base.code',2,{'jsCode':js})
def condition(name,expression):
 return node(name,'n8n-nodes-base.if',2.2,{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':str(uuid.uuid4()),'leftValue':expression,'rightValue':'','operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}})
def read(name):return node(name,'n8n-nodes-base.executeWorkflow',1.3,{'workflowId':{'__rl':True,'mode':'id','value':'DvIUXUvO0fGnXseG'},'workflowInputs':{'mappingMode':'defineBelow','value':{},'matchingColumns':[],'schema':[]},'options':{'waitForSubWorkflow':True}})
def write(name,source):
 return node(name,'n8n-nodes-base.httpRequest',4.3,{'method':'POST','url':'https://api.todoist.com/api/v1/sync','authentication':'predefinedCredentialType','nodeCredentialType':'todoistApi','sendBody':True,'contentType':'form-urlencoded','bodyParameters':{'parameters':[{'name':'commands','value':"={{ JSON.stringify($('"+source+"').first().json.commands) }}"},{'name':'resource_types','value':'[]'}]},'options':{'timeout':15000}},credentials={'todoistApi':{'id':'0pIx7HjxMuZL9Vha','name':'Todoist account'}},onError='continueRegularOutput')

def build():
 base=json.loads((ROOT/'scripts/n8n_shopping_experiment.json').read_text())
 snap=base['snapshot']
 out=next(n for n in snap['nodes'] if n['name']=='Return snapshot')
 out['parameters']['jsonOutput']=out['parameters']['jsonOutput'].replace('sectionId:t.section_id}', 'sectionId:t.section_id,parentId:t.parent_id,recurring:!!t.due?.is_recurring,uncompletable:!!t.is_uncompletable}')
 out['parameters']['jsonOutput']=out['parameters']['jsonOutput'].replace('={{ { projectId:', "={{ { request_id: 'shopping-' + $execution.id + '-' + $now.toMillis(), projectId:")
 js=(ROOT/'scripts/shopping/logic.js').read_text()
 # ponytail: single-project filesystem lock; fail closed after a crash. Manual recovery
 # only after checking the recorded execution is stopped, never a time-based lock steal.
 lock="const f=require('fs'),p='/tmp/data/shopping-apply-lock';try{f.mkdirSync(p);f.writeFileSync(p+'/owner',process.argv[1]);console.log(JSON.stringify({acquired:true}));}catch(e){if(e.code!=='EEXIST')throw e;console.log(JSON.stringify({acquired:false}));}"
 unlock="const f=require('fs'),p='/tmp/data/shopping-apply-lock';if(f.readFileSync(p+'/owner','utf8')!==process.argv[1])throw Error('lock_owner_mismatch');f.unlinkSync(p+'/owner');f.rmdirSync(p);console.log('released');"
 nodes=[node('Start','n8n-nodes-base.executeWorkflowTrigger',1.1,{'workflowInputs':{'values':[{'name':'query','type':'object'}]}}),
 node('Acquire lock','n8n-nodes-base.executeCommand',1,{'command':'=node -e '+shlex.quote(lock)+' {{ $execution.id }}'}),
 condition('Lock acquired','={{ JSON.parse($json.stdout).acquired }}'),
 code('Busy',"return [{json:{verified:false,status:'busy',message:'Another shopping request is running. No changes made.'}}];"),
 read('Read current'),
 code('Plan',js+"\nreturn [{json:plan($('Start').first().json.query,$input.first().json)}];"),
 condition('Changes needed','={{ $json.commands.length > 0 }}'),
 write('Write first','Plan'),read('Read after first'),
 code('Verify first',js+"\nlet raw={};if($('Write first').isExecuted)raw=$('Write first').first().json;return [{json:verify($('Plan').first().json,raw,$input.first().json)}];"),
 condition('Merge pending','={{ $json.commands.length > 0 }}'),
 write('Complete duplicates','Verify first'),read('Read after merge'),
 code('Verify final',js+"\nreturn [{json:verify($('Plan').first().json,combineResponses($('Write first').first().json,$('Complete duplicates').first().json),$input.first().json,true)}];"),
 code('Conflict',"return [{json:{verified:false,status:'conflict',message:'Invalid or stale plan. No changes made. Read snapshot and correct the plan.'}}];"),
 code('Failure',"return [{json:{verified:false,status:'uncertain',message:'Request stopped. Do not blindly retry; read current shopping state first.'}}];"),
 code('Result',"const {commands,...result}=$input.first().json;return [{json:result}];"),
 node('Release lock','n8n-nodes-base.executeCommand',1,{'command':'=node -e '+shlex.quote(unlock)+' {{ $execution.id }}'}),
 code('Return',"return [{json:$('Result').first().json}];")]
 connections={}
 def edge(a,b,index=0):
  main=connections.setdefault(a,{'main':[]})['main']
  while len(main)<=index:main.append([])
  main[index].append({'node':b,'type':'main','index':0})
 for a,b in [('Start','Acquire lock'),('Acquire lock','Lock acquired'),('Lock acquired','Read current'),('Read current','Plan'),('Plan','Changes needed'),('Changes needed','Write first'),('Write first','Read after first'),('Read after first','Verify first'),('Verify first','Merge pending'),('Merge pending','Complete duplicates'),('Complete duplicates','Read after merge'),('Read after merge','Verify final'),('Verify final','Result'),('Failure','Result'),('Conflict','Result'),('Result','Release lock'),('Release lock','Return')]:edge(a,b)
 for a,b in [('Lock acquired','Busy'),('Changes needed','Read after first'),('Merge pending','Result')]:edge(a,b,1)
 for n in nodes:
  if n['name'] in ['Read current','Plan','Read after first','Verify first','Read after merge','Verify final']:
   n['onError']='continueErrorOutput';edge(n['name'],'Conflict' if n['name']=='Plan' else 'Failure',1)
 for i,n in enumerate(nodes):n['position']=[(i%6)*240,(i//6)*240]
 apply={'name':'Shopping: Apply and verify','nodes':nodes,'connections':connections,'settings':{'executionOrder':'v1','executionTimeout':120,'saveDataErrorExecution':'none','saveDataSuccessExecution':'none','callerPolicy':'workflowsFromSameOwner'}}
 return base,snap,apply

if __name__=='__main__':
 base,snap,apply=build()
 for name,w in [('snapshot',snap),('apply',apply)]:
  v=call('validate_workflow',{'workflow':w});print(name,'validation',json.dumps(v),flush=True)
  assert v['valid'],v
 # Updating only these isolated experiment workflows; no existing shopping workflow touched.
 r=call('n8n_update_partial_workflow',{'id':snap['id'],'operations':[{'type':'updateNode','nodeName':'Return snapshot','updates':{'parameters':next(n for n in snap['nodes'] if n['name']=='Return snapshot')['parameters']}}]})
 saved=ROOT/'scripts/shopping/workflows.json'
 if saved.exists():
  aid=json.loads(saved.read_text())['apply']['id']
  call('n8n_update_full_workflow',{'id':aid,**apply})
 else:aid=call('n8n_create_workflow',apply)['data']['id']
 apply['id']=aid;saved.write_text(json.dumps({'apply':apply},indent=2)+'\n');print('apply',aid,flush=True)
 call('n8n_update_partial_workflow',{'id':aid,'operations':[{'type':'activateWorkflow'}]})
 # Native v1.3 supports explicit JSON Schema; v2 $fromAI(json) loses the array type.
 task={'type':'object','additionalProperties':True}
 schema={'type':'object','required':['request_id','operations'],'additionalProperties':False,'properties':{
  'request_id':{'type':'string','pattern':'^[a-zA-Z0-9_-]{12,80}$','description':'Copy from the fresh snapshot; reuse only for an identical retry.'},
  'operations':{'type':'array','minItems':1,'maxItems':25,'items':{'type':'object','required':['action'],'additionalProperties':False,'properties':{
   'action':{'type':'string','enum':['add','update','move','complete','merge']},
   **{k:{'type':'string'} for k in ['id','content','description','section']},
   'expected':task,'expected_candidates':{'type':'array','items':task},
   'duplicates':{'type':'array','items':{'type':'object','required':['id','expected'],'properties':{'id':{'type':'string'},'expected':task},'additionalProperties':False}}
  }}}}}
 tool=node('shopping_apply','@n8n/n8n-nodes-langchain.toolWorkflow',1.3,{
  'name':'shopping_apply','description':'Apply up to 25 shopping changes and verify them. Always read shopping_snapshot first. request_id: copy from shopping_snapshot and reuse only for exactly the same request. operations array: add {content,description,section,expected_candidates:[matching snapshot tasks]}; update {id,expected:snapshot task,content?,description?}; move {id,expected,section}; complete {id,expected}; merge {id:survivor,expected,duplicates:[{id,expected}]}. Section is its live name. Meaning/variants are your decision; never merge variants or invent speech. Check every result status; uncertain/partial/conflict is not success. Permanent deletion unsupported.','source':'database',
  'workflowId':{'__rl':True,'mode':'id','value':aid},
  'specifyInputSchema':True,'schemaType':'manual','inputSchema':json.dumps(schema)})
 front=call('n8n_get_workflow',{'id':base['mcp']['id']})['data']
 existing=next((n for n in front['nodes'] if n['name']=='shopping_apply'),None)
 ops=[{'type':'updateNode','nodeName':'shopping_apply','updates':{'parameters':tool['parameters'],'typeVersion':tool['typeVersion']}}] if existing else [{'type':'addNode','node':tool},{'type':'addConnection','source':'shopping_apply','target':'Shopping MCP','sourceOutput':'ai_tool','targetInput':'ai_tool'}]
 call('n8n_update_partial_workflow',{'id':front['id'],'operations':ops})
 bundle={}
 for name,wid in [('snapshot',snap['id']),('apply',aid),('mcp',front['id'])]:
  d=call('n8n_get_workflow',{'id':wid})['data'];bundle[name]={k:d[k] for k in ['id','name','nodes','connections','settings']}
 saved.write_text(json.dumps(bundle,indent=2)+'\n')
 print('Published workflow bundle',flush=True)
