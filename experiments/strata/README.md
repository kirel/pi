# Strata / llama.cpp Flash-Next prefill trial

Current deployment: [Official Strata 0.2.2 CUDA 13 image / engine 0.1.47](../../docs/strata-update-2026-10-22.md).
Previous deployment: [Official Strata 0.2.1 CUDA 13 image / engine 0.1.46](../../docs/strata-update-2026-10-20.md).
Previous deployment: [Strata 0.2.0-beta / engine 0.1.45.3](../../docs/strata-update-2026-10-19.md).
Latest parameter trial: [adapt-every 4 versus 6](../../docs/strata-adapt-benchmark-2026-10-18.md);
no reproducible decode gain, original default 4 restored. Raw observations and
checks are in `adapt-results-2026-10-18/`.
Previous deployment: [Strata 0.1.43, updated without a benchmark](../../docs/strata-update-2026-10-11.md).
Function checks are in `update-0143-results-2026-10-11/`.
Previous deployment: [Strata 0.1.42 with Expert Tail Skip active](../../docs/strata-update-2026-10-10.md).
Previous version speed comparison: [Strata 0.1.41](../../docs/strata-update-benchmark-2026-10-09.md).
Raw comparisons are in `update-0141-results-2026-10-09/`;
`benchmark_update.py` checks native request isolation, Low reasoning and KV cache state.
Earlier deployment: [Strata 0.1.40.3](../../docs/strata-update-2026-10-07.md).
Previous measurement: [Strata 0.1.40.1 cache comparison](../../docs/strata-cache-benchmark-2026-10-07.md).
The two-3090 Q3 Low layer split keeps its 2 GiB native conversation cache.
The new tail/message-boundary checkpoint selectors exclude layer splits;
their ABBA negative control and response-cache-isolated HA client rerun are
recorded in `cache-results-2026-10-07/`. Run
`python3 experiments/strata/test_cache_config.py` to check experiment restoration.

Lowest active reasoning versus NoThink:
[HA quality, extra latency and speed report](../../docs/strata-low-reasoning-benchmark-2026-10-06.md).
Raw paired observations and explicit text reviews are in
`reasoning-results-2026-10-06/`; `benchmark_reasoning.py` runs the reversible
two-3090 experiment and `summarize_reasoning.py` combines action evidence with
the recorded reviews. This experiment excludes the RTX 5060 Ti.

Measured results: [2026-10-03 benchmark report](../../docs/strata-prefill-benchmark-2026-10-03.md).
Sustained decode: [2026-10-04 benchmark report](../../docs/strata-decode-benchmark-2026-10-04.md).
Replacement assessment against 27B: [quality and direct-speed report](../../docs/strata-quality-benchmark-2026-10-04.md).
HA-focused comparison of Strata Q2, Strata Q3 and production 27B/vLLM:
[full quality and speed report](../../docs/strata-q2-q3-27b-benchmark-2026-10-04.md).
Multimodal Home Assistant / Local Hermes trial:
[setup and application checks](../../docs/strata-q3-multimodal-home-test-2026-10-05.md).
The Q3 profile now enables the native GPU image encoder; ASR/TTS remain separate.
The October 5 update introduced Strata 0.1.39 with a bounded 2 GiB native conversation
cache and disables background LLM title generation only in Local Hermes.
See the same application report and `update-results-2026-10-05/` for measurements.
Run `python3 experiments/strata/test_launcher.py` for the cache-flag check.

The test profiles are declared in `group_vars/all/llms.yml` and share the existing
`3090` swap group. Selecting one stops the previous LLM container; embedding,
ASR and TTS remain resident. The three-GPU profiles below are historical. GPU2 is now reserved for
Wolf/ComfyUI/Wan2GP and gaming; do not select those profiles for current
LLM inference or benchmarks.

```sh
uv run ansible-playbook setup.yml --tags strata-test --limit ailab-ubuntu
```

This pulls the digest-pinned official CUDA 13 image; no local compilation is needed.
The launcher resolves the ordered GPU UUIDs to live `nvidia-smi` indices and
starts the bundled API server with the packaged engine and GPU vision encoder.
The active profile uses only the two 3090s. Configs, GGUFs, prepared experts and
MTP files remain in `/home/daniel/config/llama-swap/strata-data`; the launcher
adapts executable paths in a disposable `/tmp/strata-runtime.json`, leaving the
persistent profile untouched. Profiles must already be prepared; a missing
profile fails clearly instead of implicitly downloading or building a model.
`strata-build` remains a preparation-only tag (pull image and install launcher).

| Profile | GPUs | Quant | Configured context |
| --- | --- | --- | ---: |
| `Qwen3.8-Flash-Next-Q3-3GPU` | 3090 + 3090 + 5060 Ti | existing UD-Q3_K_XL | 262144 |
| `Qwen3.8-Flash-Next-IQ2_XS-Strata` | 3090 + 3090 | GSQ-RCO IQ2_XS | 131072 |
| `Qwen3.8-Flash-Next-IQ3_XXS-Strata` | 3090 + 3090 | GSQ-RCO IQ3_XXS | 131072 |
| `Qwen3.8-Flash-Next-IQ2_XS-Strata-3GPU` | 3090 + 3090 + 5060 Ti | GSQ-RCO IQ2_XS | 131072 |

The historical text-only profiles used mapped experts, a 28 GiB container RAM
limit with no additional container swap, 8-bit KV, and
4608 MiB of VRAM reserve on each card. The limit includes reclaimable file
cache; it is not a reservation of 28 GiB. The current Q3 profile also enables
the GPU vision encoder.
The measured profiles retain `mmap`; 0.1.40's newer resident-mode support on
splits has not been evaluated here. The two-GPU profile uses automatic layer
splitting. The historical three-GPU profile uses
native `--layer-split 16,32` (16 layers per card); auto gives the 5060 Ti only
one layer in the explicit order and reduces prompt chunks to 512 tokens.

## Measurement

Copy `scripts/benchmark_flash_prefill.py` and `scripts/benchmark_qwen_serving.py`
to the GPU host. Prepare one corpus using the existing llama.cpp tokenizer:

```sh
python3 /tmp/benchmark_flash_prefill.py \
  --url http://127.0.0.1:9292/upstream/Qwen3.8-Flash-Next-Q3-3GPU \
  --model Qwen3.8-Flash-Next-Q3-3GPU --label llamacpp-q3-3gpu \
  --corpus /tmp/strata-prefill-corpus.json --prepare-only
```

Run the same command without `--prepare-only` for the baseline. Change the
URL/model/label for each Strata arm and reuse that corpus. Avoid background
downloads and other LLM traffic during measurements.

The client uses shared numeric records at 4096/16384/32768/65536/128000 raw-text
tokens, three runs per length through 64K and one near-full-context run. Actual
prompt counts include the chat template and final instruction. Two unscored
64K warmups precede each arm. Fresh system prefixes and `cache_prompt: false`
prevent reuse; more than 32 cached template-prefix tokens invalidates a run.
Every answer must be `42`. This verifies the serving path, not model quality
or long-context retrieval accuracy.

Results include both engine-reported prompt timing and actual input tokens
divided by time to first nonempty streamed token. The latter includes request
overhead and first-token work. Quantization, configured context and memory
policy differ from the baseline: this is a comparison of usable deployments,
not an isolated engine comparison.

For sustained decode, reuse the corpus with `--decode-tokens 512
--lengths 4096,65536,128000`. This requests a long German article, requires
exactly 512 output tokens and a `length` finish, and reports client throughput
as `(output_tokens - 1) / (stream_end - first_nonempty_token)` alongside native
engine timing. One short and one 64K generation warm each arm. Three measured
runs at 4K/64K and one at 128K follow; answers are retained for inspection.

For the quality comparison, also copy `scripts/evaluate_flash_quality.py` and
`experiments/strata/quality-cases-2026-10-04.json` to the GPU host. Run against
each selected backend, with a new output path for each arm:

```sh
python3 /tmp/evaluate_flash_quality.py \
  --url http://127.0.0.1:9292/upstream/Qwen3.8-Flash-Next-IQ2_XS-Strata \
  --model Qwen3.8-Flash-Next-IQ2_XS-Strata --label flash-iq2-2gpu \
  --cases /tmp/quality-cases-2026-10-04.json \
  --corpus /tmp/strata-prefill-corpus.json --output /tmp/flash-quality.jsonl
```

The suite uses fixed synthetic data and mocked tool returns. It never invokes
real Home Assistant/shopping tools. The two multi-action cases also have a
stateful follow-up in `scripts/probe_flash_tool_sequence.py`; it takes the same
URL/model/label/cases/output arguments and accepts serial calls and extra reads.
Free-text rubric scores and the first-turn protocol correction are documented
in the report; they are separate from exact JSON grades.

```sh
python3 scripts/test_benchmark_flash_prefill.py
python3 scripts/test_benchmark_qwen_serving.py
python3 scripts/test_evaluate_flash_quality.py
```

After testing, select `Qwen3.8-27B-Instruct-AutoRound-vLLM` again and verify a
real LlamaSwap completion plus embedding, ASR and TTS. Keep the test containers
unloaded; the image and model data remain cached for subsequent experiments.

The HA-focused Q2/Q3/27B comparison uses `scripts/benchmark_ha_tool_quality.py` with
captured official HA schemas and fresh simulated device state for each case.
It never executes real HA actions. Fixtures, semantic reviews, resource data,
and raw replies live in `ha-q3-results-2026-10-04/`. Recompute the published
counts with `python3 scripts/summarize_ha_tool_quality.py
experiments/strata/ha-q3-results-2026-10-04` and check the simulator with
`python3 scripts/test_benchmark_ha_tool_quality.py`.


To repeat the three-arm HA suite, first load the selected model through a normal
LlamaSwap `/v1/chat/completions` request, then run one arm at a time:

```sh
benchmark_model=Qwen3.8-Flash-Next-IQ2_XS-Strata
benchmark_label=q2
benchmark_data=experiments/strata/ha-q3-results-2026-10-04
python3 scripts/benchmark_ha_tool_quality.py \
  --url "http://ailab-ubuntu.lan:9292/upstream/$benchmark_model" \
  --model "$benchmark_model" --label "$benchmark_label" \
  --fixtures "$benchmark_data/cases.json" \
  --schemas "$benchmark_data/ha-tools-live.json" --system "$benchmark_data/system.txt" \
  --output "/tmp/$benchmark_label-ha-new.jsonl" --seeds 20261004 20261005
python3 scripts/benchmark_flash_prefill.py \
  --url "http://ailab-ubuntu.lan:9292/upstream/$benchmark_model" \
  --model "$benchmark_model" --label "$benchmark_label" \
  --corpus "$benchmark_data/capacity-corpus.json" \
  --lengths 4096,65536,128000 --repetitions 1 --decode-tokens 512 \
  > "/tmp/$benchmark_label-capacity-new.jsonl"
```

Repeat with `Qwen3.8-Flash-Next-IQ3_XXS-Strata` / `q3` and
`Qwen3.8-27B-Instruct-AutoRound-vLLM` / `27b`. For the short latency probes,
use `latency-cases.json` and seeds `20261006 20261007`. Avoid overwriting the
recorded observations; the quality runner rejects an existing output file.
Restore production and exercise embedding, TTS and ASR after the final arm.
