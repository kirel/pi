#!/usr/bin/env python3
"""Compare the deployed Q3 Low releases without changing runtime settings."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import benchmark_flash_prefill as speed

MODEL = 'Qwen3.8-Flash-Next-IQ3_XXS-Strata'
BASE = 'http://ailab-ubuntu.lan:9292/upstream/' + MODEL


def fetch(path):
    with speed.request(BASE, path) as response:
        return json.load(response)


def gpu():
    rows = subprocess.check_output([
        'ssh', '-o', 'ConnectTimeout=10', 'daniel@ailab-ubuntu.lan',
        'nvidia-smi', '-i', '0,1',
        '--query-gpu=index,temperature.gpu,utilization.gpu,clocks.current.sm,power.draw,clocks_event_reasons.sw_thermal_slowdown',
        '--format=csv,noheader,nounits'], text=True)
    return [dict(zip(('index', 'temperature_c', 'utilization', 'sm_clock_mhz',
                      'power_w', 'thermal'), [x.strip() for x in row.split(',')]))
            for row in rows.splitlines()]


def validate(before, after, result, warm):
    assert after['totals']['requests'] == before['totals']['requests'] + 1, 'Concurrent request invalidates sample'
    native = after['requests'][0]
    assert native['prompt_tokens'] == result['prompt_tokens'], 'Native request mismatch'
    assert native['finish'] == result['finish_reason'], 'Native finish mismatch'
    assert native['reused'] == result['cached_tokens'], 'Native cache mismatch'
    assert native['reused'] > 1024 if warm else native['reused'] <= 32, 'Unexpected cache state'
    return native


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label', required=True)
    p.add_argument('--version', required=True)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cooling-limit-c', type=int, default=70)
    p.add_argument('--confirm-only', action='store_true', help='Warm up, then measure one cold 64K prompt')
    a = p.parse_args()
    assert 50 <= a.cooling_limit_c <= 70
    a.output.parent.mkdir(parents=True, exist_ok=True)
    corpus = json.loads(a.corpus.read_text())
    groups = {n: [c for c in corpus if c['length'] == n] for n in (4096, 16384, 65536)}
    status = fetch('/v1/status')
    assert status['engine'] == a.version and status['activity']['in_flight'] == 0, status
    meta = dict(label=a.label, version=a.version, at=time.time(), status=status,
                corpus_sha256=hashlib.sha256(a.corpus.read_bytes()).hexdigest(),
                reasoning='low', decode_tokens=1024, cooling_limit_c=a.cooling_limit_c,
                confirm_only=a.confirm_only)
    a.output.with_suffix('.metadata.json').write_text(json.dumps(meta, indent=2) + '\n')
    with a.output.open('x') as out:
        def run(kind, length, rep=0, decode=0, warm=False):
            deadline = time.monotonic() + 600
            while True:
                cards = gpu()
                if max(int(c['temperature_c']) for c in cards) <= a.cooling_limit_c:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError(f'GPUs did not cool below {a.cooling_limit_c} C')
                time.sleep(5)
            assert fetch('/v1/status')['activity']['in_flight'] == 0, 'Another request is active'
            before = fetch('/metrics')
            assert before['engine']['version'] == a.version, 'Runtime changed during benchmark'
            source = groups[length][rep] if length else dict(length=0, text='Warmup.', seed=0)
            # The same seeds and corpus are used in every release; each cold case has its own prefix.
            seed = 202610090000 + length + rep + {'warmup': 1000000, 'cold': 0,
                    'decode': 2000000, 'warm-prime': 3000000, 'warm': 3000000, 'aux': 4000000}[kind]
            if kind == 'warm':
                source = groups[length][0]
                seed -= rep
            case = {**source, 'seed': seed}
            try:
                result = speed.generate(BASE, MODEL, case, decode, 'low', warm)
                after = fetch('/metrics')
                native = validate(before, after, result, warm)
                row = dict(label=a.label, version=a.version, kind=kind, length=length,
                           rep=rep, result=result, native=native, gpu_before=cards, gpu_after=gpu())
            except Exception as exc:
                out.write(json.dumps(dict(label=a.label, kind=kind, length=length,
                                          rep=rep, error=str(exc))) + '\n')
                out.flush()
                raise
            out.write(json.dumps(row, ensure_ascii=False) + '\n')
            out.flush()
            print(json.dumps(dict(label=a.label, kind=kind, length=length, rep=rep,
                   prompt_ms=native['prompt_ms'], decode_tok_s=native['decode_tok_s'],
                   first_visible_s=result['first_visible_s'], reused=native['reused'])), flush=True)
        run('warmup', 0)
        run('warmup', 65536)
        if a.confirm_only:
            run('cold', 65536)
            return
        for rep in range(3):
            for length in ((4096, 16384, 65536) if rep % 2 == 0 else (65536, 16384, 4096)):
                run('cold', length, rep)
        for length in (4096, 65536):
            run('decode', length, decode=1024)
        run('warm-prime', 16384)
        for rep in range(3):
            run('aux', 0, rep)
            run('warm', 16384, rep, warm=True)


if __name__ == '__main__':
    main()
