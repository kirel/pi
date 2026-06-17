# Hardware Upgrade Report: Dual-GPU Bare Metal Migration

## Status: ✅ Completed (June 2026)

### Migration Summary

| Aspect | Before (ITX, Dec 2025) | After (ATX, June 2026) |
| :--- | :--- | :--- |
| **Form Factor** | ASUS Z690 ITX | ASRock Z790 Taichi Lite |
| **Case** | ITX enclosure | Density CX3150X (3U Rackmount) |
| **GPU 0** | RTX 5060 Ti (internal, x8 riser) | RTX 3090 (direct PCIE1, x8) |
| **GPU 1** | RTX 3090 (Thunderbolt 4 eGPU) | RTX 3090 (direct PCIE2, x8) |
| **PCIe Bandwidth** | ~0.25–2 GB/s (Gen 1 degraded) | ~16 GB/s (Gen 4 x8) |
| **Virtualisation** | Proxmox VM | Bare Metal Ubuntu |
| **LLM Prefill** | Severely bottlenecked | 64x faster GPU-to-GPU handoff |

### Key Decisions
- **Motherboard:** ASRock Z790 Taichi Lite — provides true x8/x8 CPU bifurcation for the i5-12500.
- **Cooling:** Low-profile cooler (Noctua NH-D9L) to fit 3U rack height limit (115mm max).
- **Storage:** NVMe in M2_2 slot (not M2_1, which steals GPU lanes).
- **Spare GPU:** RTX 5060 Ti (Blackwell, 16 GB) removed from system — cannot be safely powered internally. Available for potential eGPU reuse.

### What Was Resolved
1. PCIe Gen 1 bottleneck from riser cable signal integrity issues.
2. Thunderbolt 4 eGPU bandwidth limitation for the RTX 3090.
3. Proxmox virtualisation overhead — now running bare metal Ubuntu.
4. Single-GPU LLM limitation — both 3090s now available for tensor-parallel inference.
