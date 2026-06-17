# PCIe & GPU Configuration (June 2026)

## Current Hardware

**Host:** `ailab-ubuntu` (Bare Metal)
**Motherboard:** ASRock Z790 Taichi Lite (LGA1700)
**CPU:** Intel i5-12500 (16 CPU PCIe 5.0 lanes, bifurcated x8/x8)

| GPU | UUID | PCIe Slot | Link | VRAM | Role |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RTX 3090 #0 | `GPU-c6f73144-...` | PCIE1 (x8) | Gen 4 x8 | 24 GB | Primary LLM inference |
| RTX 3090 #1 | `GPU-7566fbd0-...` | PCIE2 (x8) | Gen 4 x8 | 24 GB | Embeddings, STT, Immich ML, ComfyUI, Wan2GP, Wolf |

Both GPUs are plugged directly into the motherboard — no risers or eGPU enclosures.

### PCIe Gen 1 at Idle

When idle (`nvidia-smi` shows Gen 1), this is **normal power-saving behaviour**. The
link auto-negotiates back to Gen 4 under load. Persistence Mode is enabled to keep
the GPUs initialised, but the PCIe link speed still drops to Gen 1 at P8 power state.

## Spare GPU

An **RTX 5060 Ti (Blackwell, 16 GB GDDR7)** is available but not currently installed.
It cannot be safely powered internally (no spare PCIe 8-pin/12VHPWR capacity).
See the Hardware Upgrade section for options.

## GPU Power Management

Per-GPU power limits and persistence mode are configured in
`group_vars/ailab_ubuntus.yml` and applied by the `gpu` Ansible role:

- Both RTX 3090s: 250W power limit, persistence mode on
- Clock locking is available but currently not configured

## Historical Context

The system was previously an ITX build (ASUS Z690) with a single RTX 3090 connected
as a Thunderbolt 4 eGPU and an internal RTX 5060 Ti. This caused severe PCIe Gen 1
bottlenecks due to riser cable signal integrity issues. The migration to the Z790
Taichi Lite with both 3090s in direct x8/x8 slots resolved all PCIe performance
problems.
