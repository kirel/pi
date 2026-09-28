# n8n shopping MCP experiment

Historical read-only experiment. The expanded, deployed implementation and same-gateway write benchmark are documented in [the deployment report](n8n-shopping-deployment-2026-09-28.md).

## Existing setup, verified live

- n8n version: 2.4.2.
- Credential `Todoist account` (`todoistApi`, ID `0pIx7HjxMuZL9Vha`) exists and works: the experiment reads the shared shopping project with it.
- Credential `Todoist Bearer Auth` (`httpBearerAuth`, ID `WLjMsmJQL7iraU6n`) also exists. Its presence was verified; this experiment does not separately authenticate with it.
- Existing workflows `Einkaufsliste`, `Einkaufsliste Übersicht`, `Einkaufsliste Sektionen`, `Einkaufsliste aufräumen`, and `Einkaufsliste Cleanup Manager` are inactive.
- The old main workflow includes an LLM agent and a Todoist MCP client. Reactivating it would introduce another model-driven tool loop.

## Installed experiment

- [MCP endpoint workflow](https://n8n.kirelabs.org/workflow/iwne0jSsKHaOLMj0): `Experiment: Shopping MCP`.
- [Implementation workflow](https://n8n.kirelabs.org/workflow/DvIUXUvO0fGnXseG): `Experiment: Read shopping snapshot`.
- Endpoint: `https://n8n.kirelabs.org/mcp/shopping-experiment`.
- Tool: `shopping_snapshot`, called with `{}`. Optional passthrough `input` exposed by this n8n version is ignored.
- Both workflows are active. No schedules, notifications, model calls, or Todoist writes.
- Dedicated bearer credential `Shopping experiment MCP (isolated)`. Missing and invalid authentication both return HTTP 403.
- Client token is stored locally at `~/.config/n8n-shopping-experiment/token` (0600, parent 0700); no token is in this repository.
- The experiment is not registered in LiteLLM or selected by Home Assistant/Local Hermes. Existing access grants and shopping routes are unchanged.

Workflow: MCP trigger → sub-workflow tool → native HTTP requests for tasks and sections → compact snapshot. Project is fixed to `6Jhc7FCRmrMQPgW7`; callers cannot select arbitrary projects or URLs. Credentials are resolved by n8n.

Both reads use the [Todoist API v1](https://developer.todoist.com/api/v1/) with cursor pagination (100 results/page), including assigned tasks. There is no cache. GET calls retry once after one second. Execution timeout is 60 seconds; the page cap is 100 per resource. `complete` is false if pagination stops with a remaining cursor. Consumers must require `complete === true` and valid task/section arrays; tool errors are not successful empty lists. This n8n version can return workflow failures as text without MCP `isError`, so the benchmark also requires parseable, valid output.

This first experiment covers **reading the full list**, not deduplication, additions, updates, or completion. A production write tool needs a separate correctness and latency experiment covering variants, concurrent requests, idempotency, ambiguous write outcomes, and readback.

## Benchmark method

Source: [benchmark script](../scripts/benchmark_shopping_mcp.py). Deployed definitions: [workflow bundle](../scripts/n8n_shopping_experiment.json), containing credential references only.

Run inside `hermes-local` on `ailab-ubuntu` using its existing `LITELLM_API_KEY`; pass the n8n token on stdin. Compare:

1. n8n snapshot: one direct MCP call, two internal Todoist API reads.
2. Official Todoist MCP via LiteLLM: `find-tasks` and `find-sections`, sequential.
3. The same official calls in parallel, with a two-worker client.

Every result must match all task IDs, titles, descriptions, projects, sections, and section names. Count equality alone is insufficient. The official task read uses `responsibleUserFiltering=all`, `limit=100`, and follows all pages. A shopping-list change during measurement aborts the benchmark rather than comparing different states.

One warm-up cycle is recorded but excluded. Seven measured cycles per variant, rotating variant order. Timing covers the client MCP call through the complete response, with sessions initialized beforehand; urllib opens requests without a persistent connection pool for both paths. Response sizes refer to reserialized MCP result JSON, not actual wire bytes or model tokens. No private shopping contents are retained in results.

**Limits:** this compares different deployed routes: n8n directly versus official Todoist through LiteLLM. It does not isolate gateway overhead, measure LLM inference/prompt caching, or establish Assist end-to-end latency. Small samples are directional, not a tail-latency SLA. Pagination is configured for both paths, but the live dataset fits in one page per resource.

The pilot was discarded after its SSE parser failed on a response not beginning with `event:` or `data:`. The final parser accepts preceding keepalive/comment lines and selects the JSON-RPC response by ID.

## Lifecycle

To repeat, copy the benchmark script into `hermes-local` and run `python /tmp/benchmark_shopping_mcp.py`, providing the token through stdin from the protected local file over SSH. Never put it into arguments or print it. Assertions make this a correctness check as well as a timing benchmark.

To stop the experiment, deactivate `iwne0jSsKHaOLMj0` and `DvIUXUvO0fGnXseG`. Existing shopping workflows need no changes. The new bearer credential can then be deleted along with its local token file. To integrate later, add the endpoint only through `litellm_mcp_servers`, store authentication encrypted, grant the appropriate shopping group, deploy `llm-tools`, and remeasure through that same gateway before switching the Assist path.

## Results

Seven measured runs per route, plus one excluded warm-up each. All 24 snapshots matched: 28 tasks and 20 sections. No Todoist data was changed.

| Route | Median | Min–max | Client tool calls | Result JSON |
| --- | ---: | ---: | ---: | ---: |
| n8n_direct | 0.579 s | 0.534–0.622 s | 1 | 9,120 bytes |
| official_sequential_via_litellm | 6.002 s | 4.533–8.526 s | 2 | 20,453 bytes |
| official_parallel_via_litellm | 6.339 s | 4.545–19.987 s | 2 | 20,453 bytes |

For this read operation, the n8n route reduced median time by 90.4% (about 10.4× faster than the sequential official route) and result JSON by 55.4%. Parallel official requests did not improve the median in this sample. These observations include routing differences; they are not a measured voice or write-operation speedup.

Raw timing samples: [results JSON](n8n-shopping-benchmark-2026-09-28.json). Both workflows passed MCP structural validation; the three `executeOnce` advisories are intentional to avoid re-fetching sections per task page and emitting duplicate snapshots. Live credential access, result equality, and authentication denial were verified.
