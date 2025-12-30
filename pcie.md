# PCIe Performance & Investigation Summary (Dec 2025)

## 1. Current Bottleneck Analysis
*   **Hardware:** RTX 3090 (Turbo/Blower) + RTX 5060 Ti (Blackwell) on ASUS ITX Z690.
*   **Status:** Both GPUs are severely throttled to **PCIe Gen 1 speeds**.
    *   **Internal (4060 Ti):** Stuck at Gen 1 x8 (~2 GB/s).
    *   **eGPU (3090 via TB4):** Stuck at Gen 1 x4 (~1 GB/s).
*   **Root Cause:**
    1.  **Physical:** Poor signal integrity through the PCIe 3.0 riser cable on a Gen 5 motherboard.
    2.  **Design:** ITX board forces x8 width on the primary slot if the M.2_1 (top) SSD slot is populated.
    3.  **Stability:** System logs (`dmesg`) show constant `BadDLLP` errors and `Correctable Bus Errors`, forcing the kernel to demote the link to Gen 1 "Safe Mode."

## 2. Impact on LLM Performance
*   **Issue:** Prompt processing (prefill) is extremely slow during multi-GPU handoffs.
*   **Reason:** Sequential prefill requires moving ~65MB+ of activation tensors between layers. At Gen 1 speeds, the 1-2 GB/s pipe causes massive "stop-and-go" latency.
*   **Token Generation:** Less affected because moving 1 token at a time requires very low bandwidth.

## 3. Implemented Software Optimizations
*   **Llama-Server:**
    *   `--ubatch-size 1024` (Physical batching bump).
    *   `--batch-size 16384` (Logical chunking).
    *   `--poll 100` (Aggressive CPU busy-wait to reduce handoff latency).
    *   `--no-host` (Bypass redundant VRAM-to-RAM copying).
*   **GPU Tuning:**
    *   Persistence Mode enabled (keeps links active).
    *   Locked Graphics/Memory clocks applied via `nvidia-smi` to prevent power-state downshifting during idle gaps.

## 4. Hardware Upgrade Plan (The "Fix")
To escape the physical Gen 1 bottleneck, a transition to **ATX/E-ATX** is required to allow direct GPU-to-CPU connections without risers.

### Top Motherboard Recommendations (LGA1700 / Z790)
1.  **ASRock Z790 Taichi (Regular/Carrara):** Best physical spacing (1-slot air gap between GPUs). Supports true x8/x8 CPU bifurcation.
2.  **ASUS ProArt Z790-CREATOR WIFI:** 10GbE Networking + TB4. Tighter spacing but safe for blower cards (3090 Turbo).
3.  **MSI MEG Z790 ACE MAX:** Most robust signal shielding, but expensive and E-ATX.

### Critical Implementation Rules:
*   **No Risers:** Plug both GPUs directly into the motherboard slots.
*   **Avoid M2_1 Slot:** On Z790, using the top M.2 slot usually steals 8 lanes from the primary GPU. Use chipset-connected M.2 slots instead.
*   **PSU:** Minimum 1000W recommended for 3090 transients.
