#!/usr/bin/env python3
"""Recorded regression: a truthful error answer can still attempt a side effect."""
import json
from pathlib import Path
from summarize_reasoning import extra_side_effects, summarize

root=Path(__file__).with_name('reasoning-results-2026-10-06')
rows=[json.loads(line) for line in (root/'q2-none-ha.jsonl').read_text().splitlines()]
row=next(r for r in rows if (r['id'],r['seed'])==('failure-1',20261004))
assert extra_side_effects(row['result'])==['assist_satellite__HassBroadcast']
summary=summarize(root)
outcome=next(o for o in summary['q2-none']['outcomes'] if (o['id'],o['seed'])==('failure-1',20261004))
assert outcome['actions_complete'] and outcome['text_pass']
assert not outcome['semantic_passed'] and outcome['unwanted_calls']==1
assert all(summary[label]['total']==104 for label in ['q3-none','q3-low','q2-none','q2-low'])
print('Recorded unsolicited broadcast and complete paired grading checks passed')
