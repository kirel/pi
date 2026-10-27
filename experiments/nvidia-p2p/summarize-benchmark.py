#!/usr/bin/env python3
"""Validate and summarize this trial's saved measurements and 1 Hz telemetry."""
import csv
import json
from datetime import datetime
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

root = Path(__file__).parent / 'results-2026-09-29'
end_times = json.loads((root / "run-end-times.json").read_text())
summary = {}
for mode in ('off', 'on', 'custom', 'off-repeat'):
    path = root / f'{mode}.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(rows) == 14, (mode, len(rows))
    for r in rows:
        if 'metrics_delta' in r:
            assert r['metrics_delta']['prompt_tokens_total'] == sum(x['prompt_tokens'] for x in r['results']), (mode, r['case'], 'concurrent traffic')
    result = {"correctness": "FAILED: standalone custom all-reduce returns NaN; performance not valid"} if mode == "custom" else {}
    for length in (8192, 32768, 65536):
        cases = [r for r in rows if r['case'].startswith(f'prefill-{length}-')]
        assert len(cases) == 3
        for r in cases:
            assert r['metrics_delta']['prefix_cache_hits_total'] == 0
            assert r['metrics_delta']['prompt_tokens_total'] == length
        result[f'prefill_{length}_tokens_s'] = median(r['results'][0]['input_tokens_per_ttft_s'] for r in cases)
    cases = {r['case']: r for r in rows}
    result['warm_prefix_ttft_s'] = cases['warm-prefix-32768']['results'][0]['ttft_s']
    result['decode_single_tokens_s'] = cases['decode-c1']['results'][0]['decode_tokens_s']
    result['parallel_total_tokens_s'] = cases['decode-c3']['aggregate_output_tokens_per_wall_s']
    assert cases['decode-c3']['metrics_delta']['prompt_tokens_total'] == 6144

    # First two runs lacked wall timestamps. Reconstruct approximate intervals
    # backwards from final output mtime; tokenizer/HTTP setup gaps are omitted.
    cursor = end_times.get(mode, 0)
    windows = []
    for r in reversed(rows):
        end = datetime.fromisoformat(r['wall_time_utc']).timestamp() if 'wall_time_utc' in r else cursor
        elapsed = (sum(x['output_tokens'] for x in r['results']) / r['aggregate_output_tokens_per_wall_s']
                   if 'aggregate_output_tokens_per_wall_s' in r else r['results'][0]['elapsed_s'])
        if r['case'].startswith('prefill-'):
            windows.append((end - elapsed, end))
        cursor = end - elapsed
    with (root / f'{mode}-telemetry.csv').open() as f:
        telemetry = list(csv.DictReader(f, skipinitialspace=True))
    selected = []
    for r in telemetry:
        ts = datetime.strptime(r['timestamp'], '%Y/%m/%d %H:%M:%S.%f').replace(tzinfo=ZoneInfo('Europe/Berlin')).timestamp()
        if any(a <= ts <= b for a, b in windows):
            selected.append(r)
    result['thermal_window_timing'] = 'approximate, reconstructed' if mode in ('off', 'on') else 'recorded'
    result['prefill_telemetry'] = {}
    for gpu in ('0', '1'):
        data = [r for r in selected if r['index'] == gpu]
        assert data, (mode, gpu, 'missing telemetry')
        assert all(float(r['power.limit [W]'].split()[0]) == 250 for r in data)
        result['prefill_telemetry'][gpu] = dict(
            samples=len(data), peak_c=max(float(r['temperature.gpu']) for r in data),
            median_sm_mhz=median(float(r['clocks.current.sm [MHz]'].split()[0]) for r in data),
            thermal_fraction=sum(r['clocks_event_reasons.sw_thermal_slowdown'] == 'Active' for r in data) / len(data))
    summary[mode] = result
(root / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary, indent=2))
