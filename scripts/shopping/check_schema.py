#!/usr/bin/env python3
"""Read-only contract check through Local Hermes' LiteLLM key."""
import json
from benchmark import Bench

b = Bench()
tool = next(t for t in b.m.rpc('tools/list', {})['tools'] if t['name'] == 'shopping-shopping_apply')
schema = tool['inputSchema']['properties']['operations']
assert schema['type'] == 'array' and schema['items']['type'] == 'object', schema
for invalid in ('[]', {}, ["not an operation"]):
    result = b.m.rpc('tools/call', {'name': tool['name'], 'arguments': {
        'request_id': 'schema-check-no-write', 'operations': invalid}})
    assert 'did not match expected schema' in json.dumps(result), result
print('Array/object schema advertised; strings, objects and non-object items rejected.')
