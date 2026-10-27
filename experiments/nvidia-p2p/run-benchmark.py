#!/usr/bin/env python3
"""Run the existing September 22 suite after two disjoint 64K warmups.

Place benchmark_qwen_serving.py beside this file inside the vLLM container.
Only the active 3090 backend is addressed; no models are launched here.
"""
import sys
from datetime import datetime, timezone
import benchmark_qwen_serving as bench

url = 'http://127.0.0.1:5801'
model = 'Qwen3.8-27B-Instruct-AutoRound-vLLM'
label = sys.argv[1]
original_emit = bench.emit
def timestamped_emit(value):
    original_emit(dict(wall_time_utc=datetime.now(timezone.utc).isoformat(), **value))
bench.emit = timestamped_emit
for seed in (900001, 900002):
    result = bench.generate(url, model, bench.prompt(url, model, 65536, seed), 32)
    bench.emit(dict(label=label, case='warmup-64k', results=[result]))
sys.argv = [sys.argv[0], '--url', url, '--model', model, '--label', label]
bench.main()
