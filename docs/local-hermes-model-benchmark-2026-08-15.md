# Local Hermes model benchmark (2026-08-15)

## Goal

Compare `Muse-Glimmer-30B-low` and `Qwen3.8-27B-Instruct-nothink` through the
real `hermes-local` Docker agent on `ailab-ubuntu`. The benchmark deliberately
uses the Hermes API server and its normal LiteLLM MCP gateway rather than
calling the inference backends directly.

The measured surface therefore includes model routing, the Hermes agent loop,
deferred tool discovery, MCP calls, prompt-cache effects, and final response
generation. Phoenix supplies the lower-level LiteLLM spans; the benchmark
runner supplies end-to-end and tool-loop measurements that Phoenix does not
contain.

## Fixed controls

- Both models receive the same five German prompts and the same system-level
  read-only instruction.
- Each workload uses a new Hermes session ID.
- One warmup precedes each model, followed by two repetitions per workload.
- Hermes is limited to 20 agent turns for both models.
- The API-server native tool surface is temporarily reduced to `web` while the
  global LiteLLM MCP server remains enabled.
- Memory and skill-creation nudges are temporarily disabled. This is required:
  an exploratory run with the normal API tool surface caused Hermes to derive
  two Home Assistant skill hints from the benchmark prompts. Those two hints
  were removed and the original file owner/mode were restored before the
  controlled run.
- The production default model remains `home-hermes`; two additional API model
  routes select the benchmark candidates per request.

The five workloads are two read-only Home Assistant queries (openings and room
temperatures), a read-only shopping-list query, a current-version web lookup,
and a concise no-tool planning task.

## Controlled result

Run group: `local-hermes-ab-20260815T221101Z-6cf00bb7`

| Model | Passed | Median end-to-end | p95 end-to-end | Tool completions | Tool errors |
| --- | ---: | ---: | ---: | ---: | ---: |
| Muse Glimmer low | 6/10 | 8.785 s | 104.632 s | 116 | 18 |
| Qwen3.8 27B NoThink | 10/10 | 8.750 s | 48.666 s | 76 | 0 |

Per-workload end-to-end times show the cold/warm prompt-cache effect:

| Workload | Muse rep 1 | Muse rep 2 | Qwen rep 1 | Qwen rep 2 |
| --- | ---: | ---: | ---: | ---: |
| HA openings | 14.392 s, fail | 2.593 s, fail | 23.644 s, pass | 5.941 s, pass |
| HA climate | 112.785 s, fail | 3.604 s, fail | 69.138 s, pass | 9.397 s, pass |
| Shopping read | 22.034 s, pass | 4.829 s, pass | 19.207 s, pass | 8.104 s, pass |
| Web current | 94.667 s, pass | 8.182 s, pass | 10.861 s, pass | 1.145 s, pass |
| Concise planning | 9.389 s, pass | 0.161 s, pass | 5.460 s, pass | 0.301 s, pass |

The four Muse failures are exactly the two Home Assistant cases in both
repetitions. Muse repeatedly selected the discovery/describe wrappers but did
not successfully invoke the Home Assistant tool. Qwen reached
`home_assistant_GetLiveContext` in all four HA cases. "Pass" here means the run
completed with a non-empty answer, no tool error, and the expected tool family;
it is a plumbing/reliability score, not an independent semantic judge of the
private returned state.

With only ten scored observations per model, p95 and latency differences are
directional. The repeated identical prompts also deliberately demonstrate warm
prompt-cache behavior, so the median is not a cold-only inference benchmark.

## Phoenix cross-check

All relevant spans are currently in Phoenix project `default`. Local Docker
Hermes can be isolated from other consumers with
`metadata.user_api_key_team_id == "hermes-ailab"`; the key alias is
`hermes-ailab-local`. Within the benchmark time window, `llm.model_name`
separates the two backends as `Muse-Glimmer-30B` and
`Qwen3.8-27B-Instruct`.

After selecting one `litellm_proxy_request` span per model call to avoid
counting LiteLLM's nested request span twice, Phoenix reported:

| Backend | LLM calls | Prompt tokens | Completion tokens |
| --- | ---: | ---: | ---: |
| Muse Glimmer | 75 | 652449 | 11353 |
| Qwen3.8 27B | 61 | 276884 | 3523 |

Phoenix is therefore useful for model-call duration, tokens, trace inspection,
and filtering by consumer team. It is not sufficient by itself for this test:
the Hermes API SSE stream is the source for total user-visible latency, tool
sequence, tool errors, and final run status.

## Repeat procedure

Deploy the persistent access and route declarations after changing them:

```bash
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab
uv run ansible-playbook setup.yml --tags hermes-docker --limit ailab_ubuntus
```

Copy the runner and apply the temporary benchmark controls:

```bash
scp scripts/benchmark_local_hermes_models.py daniel@ailab-ubuntu.lan:/tmp/
ssh daniel@ailab-ubuntu.lan 'sudo docker cp /tmp/benchmark_local_hermes_models.py hermes-local:/tmp/'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config set memory.nudge_interval 0'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config set skills.creation_nudge_interval 0'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config set agent.max_turns 20'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes tools disable --platform api_server browser terminal file code_execution vision image_gen skills todo memory session_search delegation cronjob'
ssh daniel@ailab-ubuntu.lan 'docker restart hermes-local'
```

Run inside the container so the API-server credential is never copied or
printed:

```bash
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local python /tmp/benchmark_local_hermes_models.py --acknowledge-isolation --repetitions 2 --output /tmp/local-hermes-benchmark.json'
```

Always restore the normal runtime, including after an interrupted run:

```bash
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config unset memory.nudge_interval'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config unset skills.creation_nudge_interval'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config unset agent.max_turns'
ssh daniel@ailab-ubuntu.lan 'docker exec hermes-local hermes config unset platform_toolsets.api_server'
ssh daniel@ailab-ubuntu.lan 'docker restart hermes-local'
```

The runner checkpoints the JSON result after every completed case. The JSON
contains short output previews and should remain outside the repository because
Home Assistant and shopping responses can contain private household data.
