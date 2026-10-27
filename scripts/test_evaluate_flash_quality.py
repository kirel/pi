"""Run: python3 scripts/test_evaluate_flash_quality.py."""
import io,json
from unittest.mock import patch
import evaluate_flash_quality as e
assert e.equal({'x':1.0,'on':True},{'on':True,'x':1})
assert not e.equal({'x':True},{'x':1})
assert not e.equal({'x':1,'extra':2},{'x':1})
assert not e.equal([2,1],[1,2])
def response(message,finish='stop'):
 return io.BytesIO(json.dumps({'choices':[{'message':message,'finish_reason':finish}]}).encode())
case=dict(id='check',prompt='Read state',expected_calls=[dict(name='get_state',arguments={})],
 tools=[],mock_result={'value':7},expected={'value':7})
call={'id':'t1','type':'function','function':{'name':'get_state','arguments':'{}'}}
with patch.object(e,'request',side_effect=[response({'tool_calls':[call]},'tool_calls'),response({'content':'{"value":7}'})]):
 assert e.evaluate('unused','test',case,'greedy')['passed']
with patch.object(e,'request',return_value=response({'content':'{"value":7}'})):
 assert not e.evaluate('unused','test',case,'greedy')['passed']
with patch.object(e,'request',side_effect=[response({'tool_calls':[call]},'tool_calls'),response({'content':'```json\n{"value":7}\n```'})]):
 assert not e.evaluate('unused','test',case,'greedy')['passed']
print('JSON types, exact structure, tool loop and malformed-output checks passed')
import probe_flash_tool_sequence as seq
assert seq.shopping_state({'complete:e17','delete:b03'})=={'items':[{'id':'e17','name':'Eier','completed':True},{'id':'m12','name':'Milch','completed':False}]}
assert seq.operations({'function':{'name':'shopping_apply','arguments':'{"complete_ids":["e17"],"delete_ids":["b03"]}'}})=={'complete:e17','delete:b03'}
try: seq.operations({'function':{'name':'set_light','arguments':'{"entity_id":"light.x","on":1}'}})
except ValueError: pass
else: raise AssertionError('Boolean arguments must retain their type')
case=dict(prompt='Two lights',tools=[],expected_calls=[{'name':'set_light','arguments':{'entity_id':'light.a','on':True}},{'name':'set_light','arguments':{'entity_id':'light.b','on':False}}])
a={'id':'a','function':{'name':'set_light','arguments':'{"entity_id":"light.a","on":true}'}}
b={'id':'b','function':{'name':'set_light','arguments':'{"entity_id":"light.b","on":false}'}}
with patch.object(seq,'request',side_effect=[response({'tool_calls':[a]},'tool_calls'),response({'tool_calls':[b]},'tool_calls'),response({'content':'{"completed":true}'})]):
 assert seq.probe('unused','test',case,'greedy')['passed']
with patch.object(seq,'request',side_effect=[response({'tool_calls':[a]},'tool_calls'),response({'content':'{"completed":true}'})]):
 assert not seq.probe('unused','test',case,'greedy')['passed']
with patch.object(seq,'request',side_effect=[response({'tool_calls':[a,b]},'tool_calls'),response({'content':'Beide Aufrufe waren erfolgreich.\n{"completed":true}'})]):
 result=seq.probe('unused','test',case,'greedy');assert result['passed'] and not result['strict_json']
unexpected={'id':'other','function':{'name':'set_light','arguments':'{"entity_id":"light.other","on":true}'}}
with patch.object(seq,'request',side_effect=[response({'tool_calls':[unexpected]},'tool_calls'),response({'content':'{"completed":true}'})]):
 result=seq.probe('unused','test',case,'greedy');assert not result['passed'] and result['unsafe_calls']==1
with patch.object(seq,'request',side_effect=[response({'tool_calls':[a,b]},'tool_calls'),response({'content':'{"completed":1}'})]):
 assert not seq.probe('unused','test',case,'greedy')['passed']
print('Serial tool loops, unrequested operations and premature-success checks passed')
