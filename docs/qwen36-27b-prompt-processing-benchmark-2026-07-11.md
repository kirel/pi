# Qwen3.6 27B prompt-processing benchmark (2026-07-11)

## Goal and fixed constraints

Measure prompt-processing performance for the local dense Qwen3.6 27B backend
without changing the choices that make the complete inference stack fit:

- Model: `unsloth/Qwen3.6-27B-MTP-GGUF:UD-Q3_K_XL`
- KV pool: 376832 tokens, unified across three slots in the production profile
- KV quantization: K and V `q4_0`
- Full model offload to the two RTX 3090 GPUs
- The embedding and TTS backends remained resident on the 3090s
- Existing GPU reservations for embedding, STT, and TTS are constraints, not
  memory that may be reassigned to the LLM
- The RTX 5060 Ti remained reserved for generative media and gaming and was not
  exposed to any benchmark process

No persistent Ansible or LlamaSwap configuration was changed. Temporary server
processes were stopped after the tests, and the production 27B backend was
reloaded with its original generated command.

## Environment

- llama.cpp: build 9935, commit `f2d1c2f39`
- GPUs: 2 x RTX 3090 24 GiB, PCIe Gen4 x8 under load
- GPU topology between the 3090s: `PHB`, no NVLink/P2P link reported by
  `nvidia-smi topo -m`
- Production split: experimental tensor split
- Flash Attention: enabled
- Production logical batch / physical micro-batch defaults: 2048 / 512
- MTP: enabled, draft maximum 2; generation was limited to one token so MTP did
  not materially affect the prompt-processing result

## Workload

LlamaSwap capture 17 was used as the real-world workload:

- 17844 input tokens
- 27886-character system message
- one 25-character user message
- 29 tool definitions, 43863 serialized characters
- request body approximately 73 KiB

The message and tool payload was preserved. Streaming was disabled and output
was limited to one token. Authorization data in LlamaSwap captures was already
redacted. The prompt itself is deliberately not committed to the repository.

Each cold test used a new llama-server process and therefore had zero cached
prompt tokens. Results are single controlled observations, not multi-run means;
small differences around 1-3% should consequently be treated as directional.

## Cold prompt-processing results

| Split | Slots | Batch | Micro-batch | Prompt tok/s | Time | GPU0 MiB before request | GPU1 MiB before request | Relative to baseline |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tensor | 3 | 2048 | 512 | 1321.9 | 13.499 s | 17190 | 18699 | baseline |
| tensor | 3 | 2048 | 1024 | 1358.5 | 13.136 s | 18078 | 19587 | +2.8% |
| tensor | 3 | 2048 | 1536 | 1343.8 | 13.279 s | 18960 | 20469 | +1.7% |
| tensor | 3 | 4096 | 1024 | 1248.0 | 14.298 s | 18078 | 19587 | -5.6% |
| layer | 3 | 2048 | 1024 | 836.8 | 21.324 s | 19188 | 21891 | -36.7% |
| tensor | 1 | 2048 | 1024 | 1335.4 | 13.362 s | 17628 | 19137 | +1.0% vs baseline; -1.7% vs 3-slot/1024 |

VRAM increased by roughly 0.9 GiB per 3090 when moving from micro-batch 512 to
1024, and by another roughly 0.9 GiB per GPU at 1536. The 1024 result is only
2.8% faster in this single run, while reducing the deliberately retained
headroom. Micro-batch 1536 is both slower than 1024 and substantially more
memory-intensive.

Row split could not be benchmarked. The current CUDA build exits during model
load with `device CUDA0 does not support split buffers`. This is a capability
failure, not an out-of-memory result.

Layer split is unsuitable: it is much slower and leaves only about 2.7 GiB free
on GPU1 before request processing, below the intended headroom for the other
3090 workloads.

The single-slot profile provides no prompt-processing advantage over three
slots at the same micro-batch. It would also require a different llama-server
process under LlamaSwap, discarding the production process's GPU and host prompt
caches on every profile switch.

## Prompt-cache results

These requests ran sequentially against one fresh production-equivalent server
using batch 2048 and micro-batch 512.

| Case | Total prompt tokens | Cached | Evaluated | Prompt time |
| --- | ---: | ---: | ---: | ---: |
| Cold original | 17844 | 0 | 17844 | 13.790 s |
| Identical request | 17844 | 17827 | 17 | 224.7 ms |
| User message extended by five tokens | 17849 | 17827 | 22 | 230.2 ms |
| Same history with `enable_thinking=false` | 17846 | 17827 | 19 | 228.5 ms |

The reported token/s figure for a 17-22 token cache tail is not comparable to
large-batch cold-prefill throughput. Wall-clock prompt time and cached-token
count are the relevant measurements here.

Switching the final generation mode from Thinking to NoThink preserved the
17827-token common prefix. With stable message serialization, it does not kill
the prompt cache; only the short generation-template suffix was re-evaluated.

## Context-depth observations from real LlamaSwap activity

The following production captures predate the controlled matrix but use the
same model and production configuration. They illustrate that incremental
prompt rate depends strongly on existing context depth:

| Existing cached tokens | New prompt tokens | Reported prompt tok/s |
| ---: | ---: | ---: |
| 0 | 16182 | 1297 |
| 0 | 17844 | 1320 |
| about 16k-22k | about 2.1k-2.8k | about 1025-1141 |
| 128556 | 1040 | 444 |
| 128742 | 11680 | 561 |
| 139906 | 11023 | 542 |

The lower rate at deep context is real, but the already cached 128k-140k prefix
is not being recomputed. TTFT consists of cache restoration/management plus
evaluation of the new tail, so multiplying only the new-token count by the
reported throughput understates the other fixed cache overhead.

## Conclusions

1. Keep tensor split, three slots, batch 2048, and the current KV pool and KV
   quantization.
2. Do not create a separate single-slot LlamaSwap profile. It is not faster in
   this test and profile switching would discard warm caches.
3. Do not use layer split. Row split is unavailable in the current build.
4. Micro-batch 1024 is the only potentially useful tuning change, but the
   measured 2.8% cold-prefill gain costs about 1.8 GiB aggregate 3090 VRAM. Given
   the explicit embedding/STT/TTS headroom requirement, the evidence does not
   justify changing production from 512 yet.
5. Prompt stability and cache reuse are substantially larger latency levers
   than batch tuning. The real request fell from about 13.8 seconds cold to
   about 0.23 seconds for an identical or slightly extended warm prefix.
6. Preserve `preserve_thinking=true` and switch Think/NoThink through the
   request-level generation-template option. The controlled switch retained
   the full usable prefix.

## Follow-up benchmark, if more evidence is needed

Before considering micro-batch 1024 for production, repeat only the 512 and
1024 cases at least five times each while actively exercising the resident STT
and TTS workloads. Record peak rather than post-request VRAM and latency for all
services. Accept 1024 only if it preserves the intended GPU0/GPU1 safety margins
under simultaneous load and the confidence interval confirms a useful gain.
