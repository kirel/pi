#!/usr/bin/env python3
"""Run three bounded NCCL P2P experiments against off/default references.

Uses temporary docker-exec environments; the serving process is unchanged.
Only the existing two-3090 Qwen container is eligible.
"""
import json
import subprocess
from pathlib import Path

root = Path(__file__).parent / 'results-2026-09-30'
root.mkdir(exist_ok=True)
container = 'Qwen3.8-27B-Instruct-AutoRound-vLLM'
common = dict(NCCL_CUMEM_ENABLE='0', NCCL_P2P_LEVEL='PHB', NCCL_P2P_READ_ENABLE='0',
              NCCL_P2P_DIRECT_DISABLE='1', NCCL_DEBUG='INFO',
              NCCL_DEBUG_SUBSYS='INIT,GRAPH,P2P,SHM,NET',
              LD_LIBRARY_PATH='/usr/local/lib/python3.12/dist-packages/nvidia/nccl/lib')
variants = {
    'off': dict(NCCL_P2P_DISABLE='1'),
    'on-default': dict(NCCL_P2P_DISABLE='0'),
    'on-copy-engine': dict(NCCL_P2P_DISABLE='0', NCCL_P2P_USE_CUDA_MEMCPY='1'),
    'on-ctas4': dict(NCCL_P2P_DISABLE='0', NCCL_MIN_CTAS='4', NCCL_MAX_CTAS='4'),
    'on-ctas8': dict(NCCL_P2P_DISABLE='0', NCCL_MIN_CTAS='8', NCCL_MAX_CTAS='8'),
}
records = []
# Rotate the order between repeats so drift does not always favor the same arm.
for repeat in range(3):
    names = list(variants)
    names = names[repeat:] + names[:repeat]
    for name in names:
        for graph in (0, 1):
            cmd = ['sudo', 'docker', 'exec']
            for key, value in (common | variants[name]).items():
                cmd += ['-e', f'{key}={value}']
            cmd += [container, 'timeout', '-k', '5', '60', '/tmp/nccl-tests/build/all_reduce_perf',
                    '-b', '4K', '-e', '64M', '-f', '4', '-g', '2', '-w', '10', '-n', '100',
                    '-c', '1', '-G', str(graph)]
            result = subprocess.run(['ssh', 'daniel@ailab-ubuntu.lan', *cmd],
                                    capture_output=True, text=True, timeout=75)
            log = result.stdout + result.stderr
            (root / f'{name}-graph{graph}-repeat{repeat}.log').write_text("\n".join(line.rstrip() for line in log.splitlines()).rstrip() + "\n")
            assert log.count("NVIDIA GeForce RTX 3090") == 2 and "5060" not in log
            if name in ("on-ctas4", "on-ctas8"):
                assert f"{name[-1]} coll channels" in log, (name, "CTA switch not effective")
            assert result.returncode == 0, (name, graph, result.returncode, log[-1500:])
            assert 'Out of bounds values : 0 OK' in log, (name, graph, 'verification failed')
            rows = []
            for line in log.splitlines():
                cols = line.split()
                if len(cols) == 13 and cols[0].isdigit() and cols[2] == 'float':
                    assert cols[8] == '0' and cols[12] == '0', (name, cols)
                    rows.append(dict(bytes=int(cols[0]), out_us=float(cols[5]), out_gbs=float(cols[6]),
                                     in_us=float(cols[9]), in_gbs=float(cols[10])))
            assert len(rows) == 8, (name, graph, len(rows))
            if name != 'off':
                assert 'via P2P/IPC' in log, (name, 'not IPC P2P')
                if name == 'on-copy-engine':
                    assert 'via P2P/IPC/CE' in log, 'copy engine switch not effective'
            records.append(dict(variant=name, graph=graph, repeat=repeat, rows=rows))
            (root / 'measurements.json').write_text(json.dumps(records, indent=2) + '\n')
            print(f'{name} graph={graph} repeat={repeat}: 4KiB={rows[0]["out_us"]}us '
                  f'64MiB={rows[-1]["out_gbs"]}GB/s, correct', flush=True)
