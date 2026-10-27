# Qwen3.8 PCIe P2P trial — 2026-09-29

Keep production Qwen on **NCCL P2P disabled, Custom All-Reduce disabled**.
With the patched driver, NCCL P2P reduces uncached prefill throughput by
13–17%. More seriously, direct GPU peer reads fail data verification and the
installed vLLM CustomAllreduce returns NaN instead of the expected sum.
Its apparent decode gain is **not a valid performance result**.

The original LlamaSwap config was restored byte-for-byte. A final real chat
request returned HTTP 200 and `42` for `19 + 23`. Qwen, embedding, ASR and TTS
are ready. The experimental 615.71.09 driver remains installed; this is not a
driver rollback. GPU2 (5060 Ti) was excluded from all benchmarks.
This describes the end of the benchmark; the subsequent
[standard-driver rollback was completed and verified after reboot on September 30](../experiments/nvidia-p2p/README.md#completed-rollback-september-30).

## Serving results

Same Frozenlock Qwen3.8-27B-int4-AutoRound checkpoint, vLLM 0.27.1, TP2,
250 W per 3090, 262144 configured context, three slots, 8192 batch tokens,
4096 long-prefill threshold, FP8 KV, resident audio/embedding services.
The two 3090s connect through the CPU host bridge (PHB), without NVLink.
Driver fork revision: `c8bff5400e2fc8bda4cb9a141fb596aad607a35f`.
Exact model/image identifiers are in the raw artifacts.

| Measurement | A: P2P off | B: NCCL P2P | C: Custom AR, invalid | A2: P2P off repeat |
| --- | ---: | ---: | ---: | ---: |
| Cold 8K, input tokens / TTFT second | 2480 | 2069 | 2044 | 2490 |
| Cold 32K | 2183 | 1873 | 1858 | 2186 |
| Cold 64K | 1865 | 1621 | 1617 | 1851 |
| Repeated 32K prefix TTFT, seconds | 0.821 | 0.911 | 0.921 | 0.805 |
| Single decode, tokens/s | 60.4 | 60.8 | 62.5 | 60.2 |
| Three requests, total output tokens/s including prefill | 101.3 | 94.9 | 101.6 | 101.1 |

Order was A → B → C → A2. C initially failed CUDA graph initialization with
`custom_all_reduce.cuh:164 'invalid argument'`; disabling expandable segments
allowed startup. C changes both Custom AR and the allocator, so even without
the correctness failure it would not isolate Custom AR alone. C values are
retained only as an audit trail, not evidence of useful throughput.

The existing [September 22 method](qwen38-redhat-vllm-test-2026-09-22.md) was
reused through `scripts/benchmark_qwen_serving.py`, preceded by two disjoint
64K warmups. Cold prefill is the median of three runs; metrics confirm zero
prefix hits and exact expected prompt counts, without concurrent model traffic.
Single/parallel decode each have one case per arm; small percentage differences
are not statistically established. This run does not qualify the full 262K context
or response quality. Historical warmed production results were close to A, but
the current A/B comparison is stronger because firmware and driver changed.

## Thermal order control

A2 reproduces A within 1% on all three prefill lengths, despite running last.
Thermals therefore do not explain the main P2P regression. Throttling still
occurs at 250 W: a power limit does not guarantee staying below the temperature
limit. Cooling and clocks were not fixed, so these are operational comparisons,
not laboratory thermal controls.

| Prefill telemetry | A | B | C | A2 |
| --- | ---: | ---: | ---: | ---: |
| GPU0 median SM clock, MHz | 1425 | 1470 | 1440 | 1425 |
| GPU1 median SM clock, MHz | 1530 | 1590 | 1575 | 1515 |
| GPU0 peak, °C | 91 | 90 | 90 | 91 |
| GPU1 peak, °C | 92 | 90 | 91 | 93 |

A/B phase windows are reconstructed approximately from the final file timestamp;
C/A2 have recorded timestamps. Raw 1 Hz samples and thermal flags are retained.

## Communication measurements

NVIDIA `nccl-tests` commit `b4d5beebca8a76cf01335f724d154b9b9d394d96`
was compiled inside the production vLLM container against its NCCL 2.30.7.
`all_reduce_perf -b 4K -e 64M -f 4 -g 2 -w 10 -n 100 -c 1` exercises only
its two visible 3090s. All four NCCL runs reported zero incorrect values.

| All-Reduce payload | P2P off, out-of-place | P2P on, out-of-place |
| --- | ---: | ---: |
| 4 KiB latency, no CUDA graph | 24.38 µs | 20.64 µs |
| 1 MiB bandwidth | 6.36 GB/s | 4.45 GB/s |
| 16 MiB bandwidth | 7.67 GB/s | 4.85 GB/s |
| 64 MiB bandwidth | 7.79 GB/s | 4.91 GB/s |

For two ranks, NCCL's algorithm and bus bandwidth factors coincide. These are
collective throughput measurements, not the sum of both physical directions.
P2P is about **37% slower** at 64 MiB. Logs confirm SHM/direct versus P2P/direct
pointer. A further `-G 1` pair used `NCCL_P2P_DIRECT_DISABLE=1` for the P2P arm
to exercise **P2P/IPC**, as vLLM does: 64 MiB yielded 7.74 versus 4.93 GB/s.
Small-message graph results were 9.69 versus 20.09 µs at 4 KiB. This second
pair changes graph mode and P2P buffer access together relative to the first;
it is a confirmation of the bulk-transfer regression, not an isolated IPC-cost test.

NVIDIA CUDA 12.8 `p2pBandwidthLatencyTest` showed ~6.04 GB/s copying with peer
access disabled and ~6.83 GB/s enabled; copy latency fell from ~11–12 to ~1 µs.
The sample itself warns against treating it as a precision performance tool.
Its apparent ~10.4 GB/s SM peer-read result is **invalid**, because that path
subsequently failed nonzero-pattern verification. The sample measures timings
without validating the transferred contents.

NVIDIA `nvbandwidth` v0.10.0, commit
`82fc4e8c6afa0babb8687793678f615b3b8d793e`, independently measured
**6.83 GB/s in each direction** for `device_to_device_memcpy_read_ce`, using
512 MiB buffers, five samples and enabled data verification. Under this load
both links were PCIe **4.0 ×8**, GPUs only 53–54 °C, still capped at 250 W.
The Gen1 link seen in idle `lspci` output is power saving, not a load-time limit.
PCIe 4.0 ×8 has an encoding-limited ceiling of approximately 15.75 GB/s per
direction before packet overhead; P2P unlock does not add physical lanes.

## Correctness failure and root-cause boundary

`nvbandwidth` failed verification on write-CE, write-SM and read-SM cases at
16 MiB; write-CE also failed at 256 MiB. A failure in its remote verification
must not be mistaken for proof that every associated copy operation failed.

The independent [CUDA check](../experiments/nvidia-p2p/verify-p2p.cu) uses
16 MiB changing pseudorandom patterns and verifies every word on the CPU after
copying from the destination GPU. Both directions, three trials per path:

- CUDA peer copy: correct.
- SM kernel writing to peer memory: correct.
- SM kernel reading peer memory: all 4,194,304 words wrong, observed values
  `0xffffffff`. This is not a bandwidth measurement of valid data.

The [installed vLLM check](../experiments/nvidia-p2p/verify-custom-all-reduce.py)
then summed arrays of ones on GPU0 and twos on GPU1. Every element should be 3.
Both ranks instead returned NaN for all 1024 elements, with FP32 and BF16,
both eager and CUDA graph execution. `expandable_segments:False` was used,
matching the C arm. Passing initialization and token streaming are insufficient
correctness checks; the earlier C performance interpretation is withdrawn.

IOMMU default domain is verified **Passthrough**. Both GPU root ports initially
had ACS control `001d`. A bounded test temporarily set only `00:01.0` and
`00:01.1` to `0000`; peer-read corruption and nvbandwidth failure persisted.
Both values were restored to `001d` using an EXIT trap and verified afterward.
No persistent ACS/BIOS change was made. No NVIDIA Xid was observed.

The read/write asymmetry is consistent with a CPU/root-complex routing
limitation. A [first-hand Alder Lake investigation with a PCIe bus analyzer](https://community.intel.com/t5/Mobile-and-Desktop-Processors/P2p-capabilities-of-the-Alder-Lake-Z690-platform/td-p/1395965)
reports working writes but unsupported peer reads. That corroborates the
hypothesis; it is not proof of the exact root cause on this i5-12500/Z790 system.
The current evidence does not isolate silicon/firmware from driver mapping, nor
prove why valid P2P writes plateau at 6.8 GB/s. Doing so requires another
supported hardware path or lower-level tracing, not more identical model runs.

## Interpretation and expectation

A healthy low-latency, high-bandwidth interconnect should help tensor parallel
inference, but weights remain in each GPU's VRAM: the cards exchange intermediate
results, not the whole model every token. Compute, local VRAM reads and attention
still take time. Prefill sends larger activation tensors; decode often depends
more on small-message latency and local memory bandwidth.

Here, bulk NCCL communication actually slows down, matching slower prefill.
The model has hidden size 5120: a 4096-token BF16 activation is 40 MiB, already
larger than vLLM Custom AR's default 8 MiB eligibility limit on SM86. This is an
illustration from configuration, not a traced histogram of collective sizes.
Custom AR cannot be assumed to replace all prefill communication, and on this
machine its correctness failure overrides all performance discussion.

I would have expected a modest benefit or roughly neutral behavior from PCIe
P2P, with stronger gains only if communication dominated. A blanket large
speedup was never warranted for PCIe ×8/PHB. The measured bulk regression and
broken reads are specific reasons this configuration does not meet that expectation.

## Reproduction and artifacts

[Raw outputs](../experiments/nvidia-p2p/results-2026-09-29/) include every serving
run, telemetry, transport logs, correctness failures and the ACS countercheck.
Trailing whitespace in saved logs was normalized; measured values are unchanged.
`python3 experiments/nvidia-p2p/summarize-benchmark.py` validates counts/cache
conditions and regenerates the summary, explicitly marking Custom AR invalid.

Temporary serving mode changes use Ansible from this worktree:

```sh
ANSIBLE_VAULT_PASSWORD_FILE=/home/daniel/code/pi/.vault_pass uv run ansible-playbook experiments/nvidia-p2p/benchmark-mode.yml -e benchmark_mode=off
# Modes: off, on, custom, restore. Do not enable custom for production.
```

Copy the existing serving script beside `run-benchmark.py` inside the backend
container, then run the wrapper with a label. Restart between arms; restore the
original configuration afterward. Never run a new mode change concurrently with
a benchmark. The scripts do not reboot or modify the installed driver.

Compile `verify-p2p.cu` with `nvcc -arch=sm_86`; run with `CUDA_VISIBLE_DEVICES`
restricted to the two 3090 UUIDs in `host.txt`. Run the Custom AR check inside
the existing two-GPU vLLM container with `python3 -m torch.distributed.run
--standalone --nproc-per-node=2`, allocator expandable segments disabled.
Both checks intentionally exit nonzero when incorrect results are detected.

Reference: [NVIDIA GPU troubleshooting](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/gpu_troubleshooting.html)
recommends nvbandwidth and distinguishes P2P capability from correct operation;
[NCCL performance definitions](https://github.com/NVIDIA/nccl-tests/blob/master/doc/PERFORMANCE.md)
explain latency and bus/algorithm bandwidth.
