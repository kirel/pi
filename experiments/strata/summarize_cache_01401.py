"""Validate and summarize the recorded ABBA negative control."""
import json
from pathlib import Path
import re
import statistics
import sys

directory = Path(sys.argv[1])
rows = [json.loads(line) for line in (directory/'observations.jsonl').read_text().splitlines()]
assert len(rows) == 104, len(rows)
answers = [r for r in rows if 'answer' in r]
assert len(answers) == 96
client_rows = [json.loads(line) for line in (directory/'ha-isolated/observations.jsonl').read_text().splitlines()]
assert len(client_rows) == 48
client_answers = [r for r in client_rows if 'answer' in r]
assert len(client_answers) == 40
assert all(r['native']['finish'] == 'stop' for r in client_answers)
assert all(r['native']['finish'] == 'stop' for r in answers)
assert all(r.get('reasoning_chars', 1) > 0 for r in answers)
assert all('oom 0\n' in r['memory_events'] and 'oom_kill 0\n' in r['memory_events']
           for r in rows if r['kind'] == 'resources')
groups = {}
for enabled in (False, True):
    suffix = '-on' if enabled else '-off'
    arm = [r for r in rows if r['block'].endswith(suffix)]
    for name in ('native-16384', 'native-32768', 'ha', 'hermes'):
        if name.startswith('native'):
            length = int(name.split('-')[1])
            subset = [r for r in arm if r['kind'] == 'native-warm' and r['length'] == length]
        else:
            agent = ('conversation.home_nano_ai_agent' if name == 'ha' else
                     'conversation.local_hermes_hermes_local_ai_agent')
            subset = [r for r in client_rows if r['block'].endswith(suffix)
                      and r['kind'] == 'ha-warm' and r['agent'] == agent]
        assert len(subset) == (6 if name.startswith('native') else 8)
        native = [r['native'] for r in subset]
        groups[name + suffix] = {
            'n': len(subset),
            'median_elapsed_s': statistics.median(r['elapsed_s'] for r in subset),
            'median_prompt_s': statistics.median(r['prompt_ms']/1000 for r in native),
            'median_decode_s': statistics.median(r['decode_ms']/1000 for r in native),
            'reused_tokens_range': [min(r['reused'] for r in native), max(r['reused'] for r in native)],
            'prompt_read_range': [min(r['prompt_read'] for r in native), max(r['prompt_read'] for r in native)],
        }
        if name.startswith('native'):
            groups[name + suffix]['median_first_visible_s'] = statistics.median(r['first_visible_s'] for r in subset)
temperatures = {}
for index in (0, 1):
    values = [g['temp'] for r in answers + client_answers for g in r.get('gpus', []) if g['index'] == index]
    temperatures[str(index)] = [min(values), max(values)]
correct = sum(re.findall(r'\d+', r['answer']) == ['42'] for r in answers)
client_correct = sum(re.findall(r'\d+', r['answer']) == ['42'] for r in client_answers)
partial = directory/'interrupted-3-off.jsonl'
interrupted = [r for line in partial.read_text().splitlines()
               if (r := json.loads(line))['block'] == '3-off' and 'answer' in r] if partial.exists() else []
failure_path = directory/'failed-observation.json'
failure = json.loads(failure_path.read_text()) if failure_path.exists() else None
additional = len(interrupted) + int(failure is not None)
result = {'observations': len(answers), 'correct_arithmetic': correct,
          'isolated_client_observations': len(client_answers), 'isolated_client_correct': client_correct,
          'interrupted_additional_results': additional,
          'all_arithmetic_results': len(answers) + additional + len(client_answers),
          'all_correct_arithmetic': correct + client_correct + sum(re.findall(r'\d+', r['answer']) == ['42'] for r in interrupted),
          'interrupted_failure': failure,
          'native_low_reasoning_verified': sum('reasoning_chars' in r for r in answers),
          'temperature_c_ranges': temperatures, 'groups': groups,
          'interpretation': 'Both selectors exclude layer-split execution. Timing variation is not a feature speedup.',
          'settings': [r['runtime'] for r in rows if r['kind'] == 'settings'],
          'client_settings': [r['runtime'] for r in client_rows if r['kind'] == 'settings'],
          'client_cache_correction': 'Original HA ON samples hit LiteLLM response cache. Use only the separate isolated client rerun for HA timing and native attribution.'}
(directory/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result, indent=2))
