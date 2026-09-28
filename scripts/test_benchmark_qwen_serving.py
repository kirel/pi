"""Run with python3 scripts/test_benchmark_qwen_serving.py."""
import io
import json
from unittest.mock import patch

import benchmark_qwen_serving as bench

events = [
    {"choices": [{"text": "hello"}]},
    {"choices": [], "usage": {"prompt_tokens": 8, "completion_tokens": 2}},
]
body = b"".join(b"data: " + json.dumps(x).encode() + b"\n\n" for x in events)
body += b"data: [DONE]\n"
with patch.object(bench, "call", return_value=io.BytesIO(body)), \
        patch.object(bench.time, "monotonic", side_effect=[10, 12, 13]):
    result = bench.generate("unused", "test", [1] * 8, 2)
    assert result["ttft_s"] == 2
    assert result["decode_tokens_s"] == 1
    assert result["input_tokens_per_ttft_s"] == 4

with patch.object(bench, "call", return_value=io.BytesIO(body)):
    try:
        bench.generate("unused", "test", [1] * 8, 3)
    except RuntimeError:
        pass
    else:
        raise AssertionError("Truncated output must not produce a valid measurement")
print("SSE timing and incomplete-output checks passed")
