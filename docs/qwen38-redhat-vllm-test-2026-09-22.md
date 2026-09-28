# Qwen3.8 Red Hat / stock vLLM comparison — 2026-09-22

The Red Hat checkpoint with stock vLLM fits alongside our resident embedding,
ASR, and TTS services at the existing GPU budget. MTP3 substantially improves
short single-stream decode, but uncached prefill is slower, warm-prefix latency
is worse in this test, and full-context behavior was not successfully qualified.
Production remains on the original Frozenlock AutoRound / vLLM 0.27.1 backend.

## Measured results

The warmed repeat confirms the tradeoff under explicitly matched sampling:

| Measurement | Production, warmed repeat | Red Hat MTP3 |
| --- | ---: | ---: |
| Cold 8K prefill, tokens/s | 2441 | 1404 |
| Cold 32K prefill, tokens/s | 2159 | 1252 |
| Cold 64K prefill, tokens/s | 1831 | 1195 |
| Repeated 32K prefix, TTFT | 0.82 s | 2.18 s |
| Single decode, tokens/s | 59.9 | 119.0 |
| Three requests, output tokens/s including prefill | 102.7 | 114.0 |

MTP3 gives about 99% more short single-stream decode throughput, but 35–42%
less uncached prefill throughput in this workload. These are configuration
comparisons, not an isolation of the checkpoint, kernel, or runtime version.

All prefill rates below mean actual prompt tokens divided by time to first
nonempty streamed output, with zero prefix-cache hits for the cold cases.
They include request overhead and first-token work; they are not a pure kernel
throughput measurement. Each 8K/32K/64K value is the median of three runs.

| Measurement | Initial production baseline | Red Hat, no MTP | Red Hat, MTP3 |
| --- | ---: | ---: | ---: |
| Cold 8,192 tokens, tokens/s | 2709 | 1570 | 1404 |
| Cold 32,768 tokens, tokens/s | 2328 | 1283 | 1252 |
| Cold 65,536 tokens, tokens/s | 1826 | 1233 | 1195 |
| Repeated 32K prefix, TTFT | 0.75 s | 1.28 s | 2.18 s |
| Single decode, 256 output tokens, tokens/s | 60.4 | 62.5 | 119.0 |
| Three requests, aggregate output tokens/s including prefill | 103.8 | 83.3 | 114.0 |
| Startup-reported KV capacity | 360071 tokens | 372123 tokens | 294362 tokens |
| Startup-reported 262K concurrency | 1.37 | 1.42 | 1.12 |

Decode rate is `(output_tokens - 1) / (last_response_time - first_output_time)`;
with MTP, a first streamed chunk can contain several tokens, so this is an
approximation. Parallel tests use independent 2048-token inputs and 256 outputs
per request. Their wall-time throughput is not directly comparable to a
prefill-excluding aggregate decode claim.

## Full context and mixed load

- Production completed 260000 fresh input tokens in **273.45 s TTFT**
  (**950.8 input tokens/s**) and generated the requested output.
- Production also retrieved the exact synthetic marker `BENCH-COPPER-7419`
  from a **260047-token chat prompt**, completing in **275.55 s**.
- Red Hat without MTP produced no first output within **600 s** for the same
  260000-token performance prompt. The client timed out; no OOM or CUDA failure
  was reported. The cause was not isolated. Its subsequent functional checks
  were skipped after this failure.
- During the MTP3 260K test, TTS, ASR, and embedding remained usable: TTS took
  **11.92 s**, ASR **0.35 s** and returned the exact spoken sentence, and
  embedding returned 1024 dimensions.
- With a short math request concurrently active during this MTP3 long prefill,
  the metrics showed one **KV-cache preemption**. The short nonstreaming request had not completed after
  **135 s** and was aborted. The remaining MTP stress test was then deliberately
  stopped and production restored. This is **not** a 600-second MTP timeout or
  proof that a single isolated 262K MTP request can never finish.
- That MTP long run included deliberate concurrent load and is not a clean
  single-request speed comparison. The initial production functional checks
  passed thinking/no-thinking, a structured tool call plus its result, vision,
  and concurrent LLM/audio/embedding. The identical 260K-plus-short-chat stress
  scenario was not run on production, so its responsiveness in that scenario
  cannot be inferred from these results. Red Hat tool/vision/retrieval quality
  remains unqualified; the MTP mixed-load checker stopped on its first math call.

The advertised pool size is therefore a startup capacity estimate, not proof
of responsive full-context multi-user operation. We did not change memory
budgets, cooling, or production routing to force the new configuration to pass.

## Hardware and memory

Both RTX 3090s remain at 250 W power limits with PCIe 4.0 x8 links under load.
Topology is PHB, with CUDA P2P read support reporting CNS; there is no active
NVLink path. Both cards reached **90 C with software thermal slowdown active**
during sustained testing; recorded peaks were 92 C on GPU0 and 93 C on GPU1.
A warmed production repeat controls for the most
obvious cold-card advantage, but this is a real-host comparison, not a
thermally controlled laboratory benchmark.

Resident non-LLM allocations at preflight were 1512 MiB embedding + 1466 MiB ASR
on GPU0 and 3388 MiB TTS on GPU1. The Reddit recipe's 90% allocation would leave
only about 2458 MiB per card, less than these resident allocations. Tests kept
`--gpu-memory-utilization 0.755`; GPU2 was excluded throughout.

MTP3 initially left 3852/3454 MiB free on GPU0/GPU1; during mixed load one
snapshot showed 3108/2710 MiB free. Being able to keep the services resident does
not eliminate competition for GPU compute or KV-cache capacity.
The lowest sampled free memory across the monitored phases was 1336 MiB on GPU0
during production restart profiling, and 2272 MiB on GPU1 during the MTP mixed
load. These transient minima matter more than idle allocation alone.

## Reproduction and limits

- Runtime: `vllm/vllm-openai:v0.29.0`, pulled digest
  `sha256:c2914767605584b6d8f45686b82de173ecc99e781897aa3d0a66dacd72c51ae1`.
- Model: `RedHatAI/Qwen3.8-27B-INT4`, revision
  `7fb3aaca2d21c0db4716572945208db40cef9966` (compressed-tensors W4A16,
  calibrated FP8 KV). No AutoRound patch, forced INT8 activations, or remote
  model code was used for Red Hat.
- Both candidate arms: TP2, explicit 262144 context, three sequences, 8192
  batched tokens, 4096 long-prefill threshold, FP8 KV, prefix caching,
  `qwen3_xml` tools, `qwen3` reasoning, and data-parallel vision encoding.
  The MTP arm adds three speculative tokens. NCCL host staging is preserved;
  custom and FlashInfer all-reduce are disabled for our topology.
- This adapts the Reddit recipe to our resident services: it does not reproduce
  its 90% allocation or eight-sequence configuration.
- [Benchmark client](../scripts/benchmark_qwen_serving.py) uses synthetic numeric
  records, distinct seeded prefixes, exact token-count truncation, streaming
  timings, and before/after server counters. The tokenizer can warn about the
  longer source text before truncation; actual inference inputs are bounded to
  the stated token counts. Compilation and a short warmup precede measurements.
- Initial baseline and no-MTP runs used greedy sampling but inherited remaining
  model defaults (including the production presence penalty). MTP3 and the
  warmed baseline explicitly use zero presence/frequency penalties, repetition
  penalty 1, top-p 1, and disabled top-k. Prefer that controlled pair for the
  decode comparison. Prefill inputs are unchanged.
- The initial baseline ran while image/model downloads were being staged.
  The warmed repeat runs after downloads and after two 64K warmup prompts.
- The runnable SSE timing/truncation check is
  `python3 scripts/test_benchmark_qwen_serving.py`.

## Restoration

The canary and inert container-name reservation were removed. The original
vLLM 0.27.1 container was restarted with its existing LlamaSwap command; its
startup now reports 367604 KV tokens (1.40 full contexts). A real completion
through LlamaSwap returned `OK`, and Qwen, embedding, ASR, and TTS are all ready.
No production Ansible configuration, routing, GPU power limit, or GPU2 service
was changed. No kernel OOM or NVIDIA Xid was found in the checked test window.

After restoration, all eight short functional checks passed: thinking and
no-thinking answers, structured tool call and tool result, vision, and
concurrent LLM, audio, and embedding. Restored LLM checks used the LlamaSwap
front door. TTS took 9.87 s; ASR took 0.10 s with the correct transcript.

[Raw measurements and launch parameters](qwen38-redhat-vllm-results-2026-09-22.json)
include the initial and warmed baseline, both candidate arms, capacity/thermal
observations, and explicit abort reasons. Downloads remain cached for future
experiments; there is no running test container.

## Sources

- [Original Reddit report](https://www.reddit.com/r/LocalLLaMA/comments/1wn53le/qwen3827b_70_toks_160_toks_concurrent_10k_toks/)
- [Red Hat model and evaluation](https://huggingface.co/RedHatAI/Qwen3.8-27B-INT4)
- [vLLM 0.29 release](https://github.com/vllm-project/vllm/releases/tag/v0.29.0)

The Reddit author describes measurements from real workflows with prefix caching
as well as tuning benchmarks. The post does not provide the raw measurements
needed to equate its 10K claim to our uncached single-request prefill test.
