# Three PCIe P2P tuning tests — 2026-09-30

None of the three candidates closes the gap to the existing host-memory
transport. Keep production NCCL P2P and Custom All-Reduce disabled.
The serving process and its configuration were unchanged throughout these tests.

## Candidates and controls

Using the same `all_reduce_perf` binary built for the
[September 29 investigation](qwen38-p2p-benchmark-2026-09-29.md), inside the
existing Qwen container with only the two 3090 GPUs visible:

1. `NCCL_P2P_USE_CUDA_MEMCPY=1`: copy-engine transport.
2. `NCCL_MIN_CTAS=4 NCCL_MAX_CTAS=4`: four communication CTAs.
3. `NCCL_MIN_CTAS=8 NCCL_MAX_CTAS=8`: eight communication CTAs.

Fresh controls: P2P disabled, and P2P enabled with default communication settings.
Every arm uses `NCCL_CUMEM_ENABLE=0`, `NCCL_P2P_LEVEL=PHB`,
`NCCL_P2P_READ_ENABLE=0` and `NCCL_P2P_DIRECT_DISABLE=1`.
The last switch makes the single-process NCCL test use IPC buffers, matching the
vLLM transport rather than same-process direct pointers. This does not recreate
the complete vLLM workload or its separate worker processes.

NCCL 2.30.7, patched driver 615.71.09, kernel 6.8.0-142, both 3090s at 250 W.
Each arm was repeated three times with and without CUDA graphs: 30 runs total.
Each run used 10 warmups, 100 measured iterations, enabled data validation,
float32 sum, and eight payload sizes from 4 KiB through 64 MiB in factors of four.
Variant order was rotated between repeats. The saved runner asserts expected
GPU identities, result counts, zero incorrect values, and effective CE/CTA settings.

## Results

Out-of-place medians across the three repeats, **with CUDA graphs**:

| Configuration | 4 KiB latency, µs | 64 KiB latency, µs | 1 MiB, GB/s | 64 MiB, GB/s |
| --- | ---: | ---: | ---: | ---: |
| P2P off | 9.00 | 22.98 | 6.53 | **7.77** |
| P2P on, default | **7.61** | 29.20 | 4.52 | 4.88 |
| Test 1: copy engine | 11.11 | 32.88 | 4.43 | 4.91 |
| Test 2: four CTAs | 7.71 | 29.13 | 4.54 | 4.92 |
| Test 3: eight CTAs | 7.84 | 29.13 | 4.54 | 4.94 |

Lower latency and higher bandwidth are better. With two ranks, algorithm and
bus bandwidth factors coincide. These are NCCL collective bandwidth values,
not raw link bandwidth or the sum of directions.

Without CUDA graphs, the 64 MiB medians were respectively 7.75, 4.88, 4.91,
4.92 and 4.94 GB/s. The large-message conclusion is therefore unchanged.
All 30 runs passed both in-place and out-of-place verification at all eight sizes.
Logs confirm `P2P/IPC/CE` for the copy engine, and four/eight collective channels
for the CTA variants. These tests do not establish correct operation of direct
SM peer reads or Custom All-Reduce; those failures remain unresolved.

## Interpretation

Eight CTAs increase large-message throughput by only 1.2% over default P2P;
that remains 36.4% below the host-memory control. Four CTAs and the copy engine
similarly plateau around 4.9 GB/s. The copy-engine experiment was effective,
but selecting it does not make this collective run at the 6.8 GB/s raw-copy
rate measured previously. Collective overhead and transport buffering remain.
The exact limiting mechanism is not isolated by these results.

Default P2P reduces 4 KiB graph latency by approximately 15%, but the benefit
has reversed by 16 KiB (12.07 versus 11.43 µs), and large-message performance
is substantially worse. The three tuning candidates do not improve this balance.
The CE mode worsens 4 KiB graph latency to 11.11 µs. Forcing more CTAs does not
materially improve small-message latency.

No candidate was promoted to a new Qwen serving benchmark: none improved
bulk communication enough to justify it, and the preceding serving A/B already
showed no useful decode gain and 13–17% worse prefill with standard P2P.
The present tests are float32 communication microbenchmarks, not BF16 model
performance or response-quality qualification.

Temperature spot checks during the sweep rose from 47/46 °C to 86/81 °C,
with thermal slowdown inactive at the final sweep spot check. There is no
continuous thermal trace for this sweep, so this does not prove absence of
throttling at every instant. Rotated repeats and stable large-message results
provide a practical check against ordering effects.

Production remains `NCCL_P2P_DISABLE=1`, allocator expandable segments enabled,
and Custom All-Reduce disabled. Final real LlamaSwap chat returned HTTP 200
and `42` for `19 + 23`; Qwen, embedding, ASR and TTS reported ready.
No service restart, BIOS change, driver change, or persistent environment change
was performed. GPU2 was excluded.

## Reproduction

Run [run-nccl-tuning.py](../experiments/nvidia-p2p/run-nccl-tuning.py) from this
worktree with Python 3. It runs the native NCCL test through temporary
`docker exec -e` environments, bounded by timeout, and writes
[raw logs and measurements](../experiments/nvidia-p2p/results-2026-09-30/).
It requires the existing test binary in the Qwen container and will overwrite
the dated output files on rerun. Trailing whitespace in logs is normalized.

The per-run command is:

```sh
/tmp/nccl-tests/build/all_reduce_perf -b 4K -e 64M -f 4 -g 2 -w 10 -n 100 -c 1 -G 0
# Repeat with -G 1; temporary environment and variants are specified in the runner.
```

## ACS countercheck, later on September 30

The README's ACS recommendation had previously been checked only for transfer
correctness, not for NCCL throughput. The following comparison closes that gap.
Four arms (P2P on/off × ACS on/off), three repeats with and without CUDA graphs,
give 24 additional runs. The same IPC write-mode settings, sizes, iteration
counts and validation were used. Arm order rotated between repeats.

| Configuration | 4 KiB graph latency, µs | 64 MiB graph bandwidth, GB/s |
| --- | ---: | ---: |
| P2P off, original ACS | 8.89 | 7.78 |
| P2P on, original ACS | 7.77 | 4.88 |
| P2P on, ACS disabled | 7.65 | 4.88 |
| P2P off, ACS disabled | 8.91 | 7.78 |

Without CUDA graphs, the corresponding 64 MiB medians were 7.77, 4.88, 4.88
and 7.75 GB/s. Every in-place and out-of-place data check passed. Disabling
ACS did not improve bulk P2P performance or close the host-memory gap, so no
additional Qwen serving arm was started.

ACS was disabled temporarily by writing the PCIe ACS Control registers at
`00:01.0` and `00:01.1` from `001d` to `0000` using `setpci`. Every arm records
readback of the active values, and its EXIT trap restores and reads back the
original `001d` values. The final `lspci` output again shows the original
`SrcValid+ ReqRedir+ CmpltRedir+ UpstreamFwd+` settings on both root ports.
This changes runtime hardware control bits; no BIOS setting, kernel command
line or persistent configuration was modified. Clearing ACS cannot guarantee
that the CPU/root complex supports arbitrary peer transactions.

NVIDIA documents the
[setpci method in its ACS troubleshooting section](https://docs.nvidia.com/deeplearning/nccl/user-guide/docs/troubleshooting/gpu_troubleshooting.html#pci-access-control-services-acs),
with a PLX example and a general capability-based script. On this machine,
the Intel GPU root-port control registers are writable and the cleared values
were read back successfully.

[Raw outputs and register-control script](../experiments/nvidia-p2p/results-2026-09-30-acs/)
include all 24 runs. `run-acs-nccl.sh` accepts three positional values:
`NCCL_P2P_DISABLE`, ACS enabled (1/0), CUDA graphs (1/0). Run as root on AI Lab;
for example `bash run-acs-nccl.sh 0 0 1` tests P2P enabled with ACS disabled
and CUDA graphs. It requires original ACS values `001d` and restores them on exit.
The saved measurements JSON contains all eight sizes for each run.
