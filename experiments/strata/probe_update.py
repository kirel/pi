#!/usr/bin/env python3
"""Check cold prefill and alternating conversation reuse with synthetic prompts."""
import argparse
import json
import time
import urllib.request
from pathlib import Path


def generate(url, model, messages, limit=32, expected='42'):
    payload = dict(model=model, messages=messages, temperature=0, max_tokens=limit,
                   reasoning_effort="none", chat_template_kwargs={"enable_thinking": False},
                   stream=True, stream_options={"include_usage": True})
    req = urllib.request.Request(url.rstrip('/') + '/v1/chat/completions',
                                 json.dumps(payload).encode(), {'Content-Type': 'application/json'})
    start = time.monotonic()
    first, usage, finish = None, None, None
    content = ''
    with urllib.request.urlopen(req, timeout=600) as response:
        for line in response:
            if not line.startswith(b'data: ') or line.strip() == b'data: [DONE]':
                continue
            event = json.loads(line[6:])
            if 'error' in event:
                raise RuntimeError(event['error'])
            usage = event.get('usage') or usage
            for choice in event.get('choices', []):
                finish = choice.get('finish_reason') or finish
                delta = choice.get('delta', {})
                text = delta.get('content') or ''
                if delta.get('reasoning_content'):
                    raise AssertionError('Unexpected thinking output')
                if text and first is None:
                    first = time.monotonic()
                content += text
    elapsed = time.monotonic() - start
    assert first is not None and usage and finish == 'stop', (content, usage, finish)
    assert content.strip() == expected, content
    return dict(ttft_s=first-start, elapsed_s=elapsed, usage=usage, answer=content)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url', default='http://127.0.0.1:9292/upstream/Qwen3.8-Flash-Next-IQ3_XXS-Strata')
    p.add_argument('--model', default='Qwen3.8-Flash-Next-IQ3_XXS-Strata')
    p.add_argument('--corpus', default='/tmp/strata-prefill-corpus.json')
    p.add_argument('--label', required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    corpus = json.loads(Path(a.corpus).read_text())
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('x') as output:
        def run(case, text, system):
            messages = [{'role': 'system', 'content': system},
                        {'role': 'user', 'content': text + '\nIgnore the records. What is 19 + 23? Answer only 42.'}]
            result = dict(label=a.label, case=case, started_at=time.time(),
                          **generate(a.url, a.model, messages))
            line = json.dumps(result)
            output.write(line + '\n')
            output.flush()
            print(line, flush=True)
        run('warmup', '', 'Synthetic update test.')
        for length in [4096, 16384, 65536]:
            text = next(c['text'] for c in corpus if c['length'] == length)
            run('cold-' + str(length), text, 'Independent cold test ' + str(length))
        long_text = next(c['text'] for c in corpus if c['length'] == 16384)
        for i in range(3):
            run('alternating-long-' + str(i), long_text, 'Synthetic persistent HA conversation.')
            run('alternating-short-' + str(i), '', 'Synthetic separate auxiliary conversation.')


if __name__ == '__main__':
    main()
