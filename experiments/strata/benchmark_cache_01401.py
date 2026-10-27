#!/usr/bin/env python3
"""Reversible ABBA test of native tail/boundary caching on the production Q3 split.

Run on the Ansible controller. Only arithmetic goes through real HA; no action
tools are requested. Existing credentials are consumed inside the proxy process.
"""
import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
import time
import urllib.request

MODEL = 'Qwen3.8-Flash-Next-IQ3_XXS-Strata'
GPU_HOST = 'daniel@ailab-ubuntu.lan'
BASE = 'http://ailab-ubuntu.lan:9292/upstream/' + MODEL


def remote(host, argv, code=None):
    return subprocess.check_output(['ssh', '-o', 'ConnectTimeout=10', host,
                                    shlex.join(argv)], input=code, text=True)


def request(url, payload=None, timeout=600):
    data = None if payload is None else json.dumps(payload).encode()
    return urllib.request.urlopen(urllib.request.Request(
        url, data, {'Content-Type': 'application/json'}), timeout=timeout)


def metrics():
    with request(BASE + '/metrics') as response:
        return json.load(response)


CONFIG = r'''
import json, os, sys
from pathlib import Path
cfg = Path('/home/daniel/config/llama-swap/strata-data/config/strata-iq3_xxs-vision-gpu.json')
backup = Path('/tmp/strata-cache-01401-benchmark-backup.json')
mode = sys.argv[1]
if mode == 'backup':
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as out: out.write(cfg.read_text())
elif mode == 'restore':
    cfg.write_text(backup.read_text())
    backup.unlink()
else:
    c = json.loads(backup.read_text())
    c['args'] = [a for a in c['args'] if a != '--prompt-cache-tail']
    enabled = mode == 'on'
    if enabled: c['args'].append('--prompt-cache-tail')
    c.setdefault('env', {})['STRATA_CACHE_MESSAGE_BOUNDARY'] = '1' if enabled else '0'
    cfg.write_text(json.dumps(c, indent=1) + '\n')
    print(json.dumps({'prompt_cache_tail': enabled, 'message_boundary': enabled,
                      'gpus': c.get('gpus'), 'layer_split': c.get('layer_split'),
                      'prompt_cache_args': [a for a in c['args'] if 'prompt-cache' in a]}))
'''

RUNTIME = r'''
import json
from pathlib import Path
for p in Path('/proc').iterdir():
    if not p.name.isdigit(): continue
    try:
        args = (p / 'cmdline').read_bytes().decode().strip('\0').split('\0')
        if not args or not args[0].endswith('/engine/strata'): continue
        env = dict(x.split('=', 1) for x in (p / 'environ').read_bytes().decode().split('\0') if '=' in x)
        flags = {}
        for flag in ('--prompt-cache', '--prompt-cache-every', '--gpus', '--layer-split', '--turn-token'):
            if flag in args: flags[flag] = args[args.index(flag)+1]
        print(json.dumps({'flags': flags, 'tail': '--prompt-cache-tail' in args,
                          'message_boundary': env.get('STRATA_CACHE_MESSAGE_BOUNDARY', '0'),
                          'cuda_visible': env.get('CUDA_VISIBLE_DEVICES')}))
        break
    except (OSError, UnicodeError): continue
else: raise RuntimeError('Native engine process missing')
'''

# No secrets or HA context are returned: only synthetic replies and native timing.
HA = r'''
import json, re, sys, time, urllib.request, yaml
cfg = yaml.safe_load(open('/app/config.yaml'))
mcp = cfg['mcp_servers']['home_assistant']
ha = mcp['url'].removesuffix('/api/mcp')
headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + mcp['auth_value']}
native = 'http://ailab-ubuntu.lan:9292/upstream/Qwen3.8-Flash-Next-IQ3_XXS-Strata/metrics'
label = sys.argv[1]
for agent in ('conversation.home_nano_ai_agent', 'conversation.local_hermes_hermes_local_ai_agent'):
    conversation = None
    for i, expression in enumerate(('19 plus 23', '20 plus 22', '21 plus 21', '84 geteilt durch 2', '40 plus 2')):
        with urllib.request.urlopen(native, timeout=10) as response: before = json.load(response)
        previous_time = before['requests'][0]['time'] if before['requests'] else None
        body = {'agent_id': agent, 'language': 'de', 'text':
                'Reiner Rechentest: Wie viel ist ' + expression + '? Antworte nur mit der Zahl. '
                'Keine Werkzeuge verwenden und keine Geräte ändern. '
                'Ignoriere die Kennung dieses Testlaufs: ' + label + '-' + str(time.time_ns()) + '.'}
        if conversation: body['conversation_id'] = conversation
        t = time.monotonic()
        req = urllib.request.Request(ha + '/api/conversation/process', json.dumps(body).encode(), headers)
        with urllib.request.urlopen(req, timeout=600) as response: reply = json.load(response)
        elapsed = time.monotonic() - t
        conversation = reply['conversation_id']
        answer = reply['response']['speech']['plain']['speech']
        math_pass = re.findall(r'\d+', answer) == ['42']
        with urllib.request.urlopen(native, timeout=10) as response: m = json.load(response)
        latest = m['requests'][0]
        assert latest['time'] != previous_time, 'No new Strata request: response cache must not enter the timing comparison'
        assert latest['finish'] == 'stop', latest
        row = {'block': label, 'kind': 'ha-prime' if i == 0 else 'ha-warm',
               'agent': agent, 'rep': i, 'elapsed_s': elapsed, 'answer': answer, 'math_pass': math_pass,
               'native': latest, 'engine': m['engine']['version'], 'backend_call_verified': True,
               'gpus': m.get('hardware', {}).get('gpus', [])}
        print(json.dumps(row), flush=True)
'''


def generate(messages):
    payload = dict(model=MODEL, messages=messages, reasoning_effort='low',
                   chat_template_kwargs={'enable_thinking': True}, temperature=0,
                   max_tokens=256, stream=True, stream_options={'include_usage': True})
    start = time.monotonic()
    first_thought = first_visible = None
    visible = thought = ''
    usage = finish = None
    with request(BASE + '/v1/chat/completions', payload) as response:
        for line in response:
            if not line.startswith(b'data: ') or line.strip() == b'data: [DONE]': continue
            event = json.loads(line[6:])
            assert 'error' not in event, event
            usage = event.get('usage') or usage
            for choice in event.get('choices', []):
                finish = choice.get('finish_reason') or finish
                delta = choice.get('delta', {})
                if delta.get('reasoning_content'):
                    if first_thought is None: first_thought = time.monotonic() - start
                    thought += delta['reasoning_content']
                if delta.get('content'):
                    if first_visible is None: first_visible = time.monotonic() - start
                    visible += delta['content']
    elapsed = time.monotonic() - start
    assert finish == 'stop', (finish, visible)
    assert thought and usage, 'Low reasoning must be active'
    measured = metrics()
    latest = measured['requests'][0]
    assert latest['prompt_tokens'] == usage['prompt_tokens'], (latest, usage)
    return dict(elapsed_s=elapsed, first_thought_s=first_thought, first_visible_s=first_visible,
                answer=visible, math_pass=re.findall(r'\d+', visible) == ['42'],
                reasoning_chars=len(thought), usage=usage, native=latest,
                gpus=measured.get('hardware', {}).get('gpus', []))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--blocks', default='0,1,2,3', help='ABBA block indices; append when completing an interrupted run')
    p.add_argument('--ha-only', action='store_true', help='Client-path recheck with per-block response-cache isolation')
    a = p.parse_args()
    corpus = json.loads(a.corpus.read_text())
    a.output.mkdir(parents=True, exist_ok=True)
    assert metrics()['engine']['version'] == '0.1.40'
    remote(GPU_HOST, ['sudo', 'python3', '-', 'backup'], CONFIG)
    try:
        with (a.output / 'observations.jsonl').open('a' if a.blocks != '0,1,2,3' else 'x') as out:
            def save(row):
                line = json.dumps(row)
                out.write(line + '\n'); out.flush()
                print(line, flush=True)
            for block in map(int, a.blocks.split(',')):
                enabled = (False, True, True, False)[block]
                label = str(block) + ('-on' if enabled else '-off')
                settings = json.loads(remote(GPU_HOST, ['sudo', 'python3', '-', 'on' if enabled else 'off'], CONFIG))
                remote(GPU_HOST, ['docker', 'restart', MODEL])
                # The restart loads the same pinned image/config, not another GPU profile.
                for attempt in range(180):
                    try:
                        m = metrics()
                        if m.get('engine', {}).get('version') == '0.1.40': break
                    except Exception: pass
                    time.sleep(2)
                else: raise RuntimeError('Strata did not become ready')
                runtime = json.loads(remote(GPU_HOST, ['docker', 'exec', '-i', MODEL,
                                                       '/opt/strata/.venv/bin/python', '-'], RUNTIME))
                assert runtime['tail'] == enabled and runtime['message_boundary'] == str(int(enabled)), runtime
                assert len(runtime['cuda_visible'].split(',')) == 2 and '--layer-split' in runtime['flags'], runtime
                save(dict(block=label, kind='settings', settings=settings, runtime=runtime, engine=m['engine'],
                          gpu=remote(GPU_HOST, ['nvidia-smi', '--query-gpu=index,name,temperature.gpu,memory.used',
                                               '--format=csv,noheader'])))
                for length in (() if a.ha_only else (16384, 32768)):
                    text = next(c['text'] for c in corpus if c['length'] == length)
                    history = [
                        {'role': 'system', 'content': 'Synthetic cache test ' + label + '-' + str(length) +
                         '. Ignore the records. Solve only the final arithmetic question and answer only the number.'},
                        {'role': 'user', 'content': text},
                        {'role': 'assistant', 'content': 'Records received.'}]
                    for rep, expression in enumerate(('19 + 23', '20 + 22', '21 + 21', '84 / 2')):
                        result = generate(history + [{'role': 'user', 'content': 'What is ' + expression + '?'}])
                        if rep: assert result['native']['reused'] > 8192, result
                        save(dict(block=label, kind='native-prime' if rep == 0 else 'native-warm',
                                  length=length, rep=rep, **result))
                        # Park/restore the long prefix around a separate short request.
                        if rep < 3:
                            aux = generate([{'role': 'system', 'content': 'Separate auxiliary math.'},
                                            {'role': 'user', 'content': 'What is 19 + 23? Answer only the number.'}])
                            save(dict(block=label, kind='auxiliary', length=length, rep=rep, **aux))
                rows = remote('root@homelab-nuc.lan', ['docker', 'exec', '-i', 'litellm-proxy-container',
                                                    'python', '-', label], HA)
                for line in rows.splitlines(): save(json.loads(line))
                save(dict(block=label, kind='resources',
                          memory_events=remote(GPU_HOST, ['docker', 'exec', MODEL, 'cat', '/sys/fs/cgroup/memory.events']),
                          gpu=remote(GPU_HOST, ['nvidia-smi', '--query-gpu=index,name,temperature.gpu,memory.used',
                                               '--format=csv,noheader'])))
    finally:
        remote(GPU_HOST, ['sudo', 'python3', '-', 'restore'], CONFIG)
        remote(GPU_HOST, ['docker', 'restart', MODEL])
        print('Restored original native config; experimental flags removed.', flush=True)


if __name__ == '__main__': main()
