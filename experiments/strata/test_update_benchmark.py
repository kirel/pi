"""Reject contaminated or falsely warm benchmark samples."""
from benchmark_update import validate

before = {'totals': {'requests': 2}}
native = {'prompt_tokens': 16390, 'finish': 'stop', 'reused': 16384}
after = {'totals': {'requests': 3}, 'requests': [native]}
result = {'prompt_tokens': 16390, 'finish_reason': 'stop', 'cached_tokens': 16384}
assert validate(before, after, result, True) is native
for changed, warm in [({**after, 'totals': {'requests': 4}}, True),
                      (after, False),
                      ({**after, 'requests': [{**native, 'prompt_tokens': 16400}]}, True)]:
    try:
        validate(before, changed, result, warm)
    except AssertionError:
        pass
    else:
        raise AssertionError('Contaminated sample accepted')
print('Benchmark isolation and cache checks passed')
