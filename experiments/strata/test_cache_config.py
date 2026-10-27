"""Exercise the benchmark's actual reversible configuration helper."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from benchmark_cache_01401 import CONFIG, HA, RUNTIME

compile(HA, 'HA', 'exec')
compile(RUNTIME, 'RUNTIME', 'exec')
with tempfile.TemporaryDirectory() as directory:
    cfg, backup = Path(directory)/'config.json', Path(directory)/'backup.json'
    original = json.dumps({'args': ['--prefill', 'auto'], 'env': {'PRESERVE': 'yes'}})
    cfg.write_text(original)
    code = CONFIG.replace('/home/daniel/config/llama-swap/strata-data/config/strata-iq3_xxs-vision-gpu.json', str(cfg))
    code = code.replace('/tmp/strata-cache-01401-benchmark-backup.json', str(backup))
    for mode in ('backup', 'on', 'on', 'off', 'restore'):
        subprocess.run([sys.executable, '-', mode], input=code, text=True, check=True, capture_output=True)
        current = json.loads(cfg.read_text())
        assert current['env']['PRESERVE'] == 'yes'
        if mode == 'on':
            assert current['args'].count('--prompt-cache-tail') == 1
            assert current['env']['STRATA_CACHE_MESSAGE_BOUNDARY'] == '1'
        if mode == 'off':
            assert '--prompt-cache-tail' not in current['args']
            assert current['env']['STRATA_CACHE_MESSAGE_BOUNDARY'] == '0'
    assert cfg.read_text() == original and not backup.exists()
print('Cache benchmark configuration restoration passed')
