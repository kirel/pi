#!/usr/bin/env python3
from benchmark_ha_tool_quality import apply,simulate,validate
entities=[dict(name='Lampe',area='Küche',domain='light',state='off'),dict(name='Lampe',area='Büro',domain='light',state='on')]
ops,result=simulate('intent__HassTurnOff',{'name':'Lampe'},entities)
assert not ops and result['success'] is False
ops,_=simulate('intent__HassTurnOn',{'name':'Lampe','area':'Küche','domain':['light']},entities)
apply(entities,ops)
_,state=simulate('homeassistant__GetLiveContext',{'area':'Küche'},entities)
import json
assert json.loads(state['result'].split('\n',1)[1])[0]['state']=='on'
try:validate({'position':True},{'type':'object','properties':{'position':{'type':'integer','minimum':0,'maximum':100}}})
except ValueError:pass
else:raise AssertionError('Boolean accepted as integer')

ops,result=simulate('intent__HassTurnOn',{'name':'Missing'},entities)
assert not ops and result['success'] is False

ops,result=simulate('intent__HassTurnOn',{'name':'Lampe','area':'Küche','device_class':['switch']},entities)
assert not ops and result['success'] is False
entities[0]['entity_id']='light.lampe_kueche'
_,result=simulate('homeassistant__GetLiveContext',{'name':'light.lampe_kueche'},entities)
assert result['success']

from benchmark_ha_tool_quality import live_context
view=live_context([dict(name='L',area='R',domain='light',state='on',brightness=20),dict(name='M',area='R',domain='media_player',state='paused',volume_level=35)])
infos=json.loads(view['result'].split('\n',1)[1])
assert infos[0]['attributes']['brightness']=='51'
assert infos[1]['attributes']['volume_level']==0.35
print('HA selectors, state updates, entity IDs, units and argument types passed')

from benchmark_ha_tool_quality import operation,semantic_ops
turn_off={operation('Lampe','Küche','on',False)}
assert semantic_ops({operation('Lampe','Küche','brightness',0)},turn_off)==turn_off
assert semantic_ops({operation('Lampe','Büro','brightness',0)},turn_off)!=turn_off
turn_on={operation('Lampe','Küche','on',True)}
assert semantic_ops({operation('Lampe','Küche','brightness',100)},turn_on)==turn_on
assert semantic_ops({operation('Lampe','Küche','brightness',100)},set())
print('Equivalent light on/off calls accepted; other targets remain guarded')

# Regression cases from recorded model replies: success text alone is insufficient.
from pathlib import Path
import subprocess,sys
repo=Path(__file__).resolve().parents[1]
results=repo/'experiments/strata/ha-q3-results-2026-10-04'
subprocess.run([sys.executable,str(repo/'scripts/summarize_ha_tool_quality.py'),str(results)],check=True,stdout=subprocess.DEVNULL)
summary=json.loads((results/'summary.json').read_text())
def outcome(label,case,seed):
    return next(o for o in summary[label]['outcomes'] if (o['id'],o['seed'])==(case,seed))
assert outcome('q2','light-0',20261004)['passed']
assert not outcome('q2','clarify-7',20261004)['passed']
assert not outcome('q3','followup-brighter',20261004)['passed']
assert not outcome('27b','state-7',20261004)['passed']
assert summary['latency']['paired_correct_n']==11
assert summary['latency']['excluded']==[['light-1',20261006]]
print('Recorded equivalent action, cancellation, false-success and invented-state regressions passed')
