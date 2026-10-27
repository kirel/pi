"""Run with python3 scripts/test_benchmark_flash_prefill.py."""
import io
import json
from unittest.mock import patch

import benchmark_flash_prefill as bench


def body(cached=0, answer="42", output_tokens=2, finish_reason="stop"):
    events = [{"choices": [{"delta": {"content": answer}}]},
              {"choices": [{"delta": {}, "finish_reason": finish_reason}],
               "usage": {"prompt_tokens": 8, "completion_tokens": output_tokens,
                                         "prompt_tokens_details": {"cached_tokens": cached}}}]
    return io.BytesIO(b"".join(b"data: " + json.dumps(x).encode() + b"\n\n" for x in events))


case = dict(length=8, seed=1, text="Records")
with patch.object(bench, "request", return_value=body()), \
        patch.object(bench.time, "monotonic", side_effect=[10, 12, 13]):
    result = bench.generate("unused", "test", case)
    assert result["ttft_s"] == 2 and result["input_tokens_per_ttft_s"] == 4
for cached, answer in [(100, "42"), (0, "wrong"), (0, "")]:
    with patch.object(bench, "request", return_value=body(cached, answer)):
        try:
            bench.generate("unused", "test", case)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Cached, wrong or empty output must invalidate the measurement")
with patch.object(bench, "request", return_value=body(answer="word "*150, output_tokens=512, finish_reason="length")), \
        patch.object(bench.time, "monotonic", side_effect=[10, 12, 22]):
    result = bench.generate("unused", "test", case, decode_tokens=512)
    assert result["decode_s"] == 10 and result["output_tokens_per_decode_s"] == 51.1
for tokens, finish in [(511, "length"), (512, "stop")]:
    with patch.object(bench, "request", return_value=body(answer="word "*150, output_tokens=tokens, finish_reason=finish)):
        try:
            bench.generate("unused", "test", case, decode_tokens=512)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Short or prematurely terminated decode must invalidate the measurement")
print("Prefill/decode timing, cache and output checks passed")

# Reasoning can arrive before speech; these must remain separate latency measures.
events=[{'choices':[{'delta':{'reasoning_content':'Calculate.'}}]},
        {'choices':[{'delta':{'content':'42'},'finish_reason':'stop'}],
         'usage':{'prompt_tokens':8,'completion_tokens':4,'prompt_tokens_details':{'cached_tokens':0}}}]
stream=io.BytesIO(b''.join(b'data: '+json.dumps(e).encode()+b'\n\n' for e in events))
with patch.object(bench,'request',return_value=stream) as send, \
        patch.object(bench.time,'monotonic',side_effect=[10,12,14,15]):
    result=bench.generate('unused','test',case,reasoning_effort='low')
    assert result['ttft_s']==2 and result['first_visible_s']==4
    assert result['reasoning']=='Calculate.'
    assert send.call_args.args[2]['chat_template_kwargs']=={'enable_thinking':True}
    assert send.call_args.args[2]['reasoning_effort']=='low'
print('Low reasoning request and separate visible latency passed')
