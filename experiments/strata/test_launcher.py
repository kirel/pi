"""Check migration paths, GPU selection, cache flags and source preservation."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

launcher = Path(__file__).parents[2] / 'roles/llm_inference/files/strata-start.sh'
code = launcher.read_text().split('"$python" - "$cfg" "$gpu_indices" <<\'PY\'\n')[1].split('\nPY\n')[0]
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory) / 'config.json'
    output = Path(directory) / 'runtime.json'
    original = json.dumps({'args': ['--expert-profile', '/opt/strata/data/expert-profile.bin',
                                   '--conversation-cache-mib', '1024'],
                           'vision': {'gpu': True, 'mmproj': '/data/models/mmproj.gguf'}})
    path.write_text(original)
    component = SimpleNamespace(expand=lambda *_: '/components/engine/strata',
                                package_lib_dirs=lambda p: [str(p)])
    env = {'STRATA_CONVERSATION_CACHE_MIB': '2048', 'STRATA_CONVERSATION_CACHE_SLOTS': '4',
           'STRATA_LAYER_SPLIT': 'auto', 'PORT': '5804'}
    code = code.replace('/tmp/strata-runtime.json', str(output))
    with patch.dict(sys.modules, {'strata_control': SimpleNamespace(engine_component=component)}), \
         patch.object(sys, 'argv', ['-', str(path), '1,0']), patch.dict(os.environ, env):
        for _ in range(2):
            exec(compile(code, str(launcher), 'exec'), {})
        cfg = json.loads(output.read_text())
        assert path.read_text() == original
        assert cfg['gpu'] == [1, 0] and cfg['layer_split'] == 'auto'
        assert cfg['exe'] == '/components/engine/strata'
        assert cfg['lib_dirs'] == ['/components/engine']
        assert cfg['vision'] == {'gpu': True, 'mmproj': '/data/models/mmproj.gguf',
                                 'exe': '/components/engine/strata-vision'}
        assert cfg['args'][:2] == ['--expert-profile', '/opt/strata/terminal/data/expert-profile.bin']
        assert cfg['args'].count('--conversation-cache-mib') == 1
        assert cfg['args'][cfg['args'].index('--conversation-cache-mib')+1] == '2048'
        os.environ['STRATA_CONVERSATION_CACHE_MIB'] = '0'
        exec(compile(code, str(launcher), 'exec'), {})
        assert json.loads(output.read_text())['args'] == cfg['args'][:2]
print('Launcher migration and cache configuration passed')
