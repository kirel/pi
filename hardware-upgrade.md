# Hardware Upgrade Report: Dual-GPU Workstation Migration (End-2025)

## 1. Executive Summary
- **Current Setup:** ITX Bottleneck (Gen 1 x1 link, ~250MB/s handoff).
- **Target Setup:** ATX/E-ATX Workstation (Gen 4/5 x8/x8 link, ~16,000MB/s handoff).
- **Key Insight:** Your **ASUS Turbo 3090 (Blower)** is the "MVP" of this upgrade. Its blower design allows it to work perfectly in tight "GPU sandwich" configurations without overheating.
- **Compatibility:** Staying on **Z790 (LGA1700)** to keep your i5-12500.

---

## 2. The PCIe Lane Architecture (LGA1700)
Your i5-12500 has **16 lanes** of PCIe 5.0 for graphics. On a high-end motherboard, these are bifurcated into **two x8 slots** directly wired to the CPU.

| Configuration | Interconnect Speed | LLM Prefill Impact |
| :--- | :--- | :--- |
| **Current ITX** | 0.25 GB/s (Gen 1 x1) | **Severe bottleneck** |
| **Bifurcated x8/x8** | **15.8 GB/s (Gen 4 x8)** | **64x Faster Handoff** |

---

## 3. Motherboard Options (Late 2025 Availability)

The "Taichi Lite" is no longer available. We must move to the premium segment to secure true x8/x8 CPU bifurcation.

### **1st Choice: ASRock Z790 Taichi (Regular or Carrara)**
*   **Reasoning:** The best physical layout for dual-GPU cooling.
*   **Pros:** PCIE1 and PCIE2 are separated by **3 slots**. With two 2-slot cards, you get a **1-slot air gap**.
*   **Cons:** **E-ATX Form Factor** (Requires a wide case).
*   **Storage:** 5x M.2 slots (Avoid M2_1 to preserve GPU lanes).
*   **Price:** ~$450.

### **2nd Choice: ASUS ProArt Z790-CREATOR WIFI**
*   **Reasoning:** Professional workstation features (10GbE + TB4).
*   **Pros:** **10GbE Ethernet** is huge for homelabs. Thunderbolt 4 built-in.
*   **Cons:** PCIE1 and PCIE2 are separated by only **2 slots**. Your cards will be **flush against each other**.
*   **Blower Advantage:** Since your 3090 is a Blower card, this "GPU Sandwich" is thermally safe.
*   **Price:** ~$440.

### **3rd Choice: Gigabyte Z790 AORUS MASTER X**
*   **Reasoning:** Extreme signal stability and overbuilt VRMs.
*   **Pros:** Excellent trace quality ensures Gen 4/5 stability without errors.
*   **Cons:** Also **E-ATX**. BIOS settings for bifurcation can be complex.
*   **Price:** ~$480.

---

## 4. Component Compatibility Checklist

| Component | Status | Note |
| :--- | :--- | :--- |
| **CPU** | Keep (i5-12500) | Fully supports x8/x8 bifurcation. |
| **RAM** | **Upgrade Likely** | Most premium Z790 boards are **DDR5 only**. |
| **Case** | **SELECTED** | **Density CX3150X (3U Rackmount)**. Fits E-ATX up to 12"x13". |
| **Cooling** | **NEW LIMIT** | **115mm Max Height**. Needs low-profile cooler (e.g. Noctua NH-D9L). |
| **PSU** | **Check Wattage** | Recommend **1000W ATX 3.0** to handle 3090 transients. |
| **Riser** | **DISCARD** | Both GPUs must plug **DIRECTLY** into the motherboard. |

---

## 5. Final Recommendation & Plan
1.  **Primary Path:** Buy the **ASRock Z790 Taichi** and the **Density CX3150X (3U Rackmount)**.
2.  **Mounting:** Put the **4060 Ti in PCIE1 (Top)** and the **3090 Turbo in PCIE2 (Bottom)**.
    - The blower fan on the bottom will have its own intake space in the rack airflow path.
    - The 4060 Ti on top will stay cool thanks to the empty slot gap provided by the Taichi layout.
3.  **Storage:** Plug your NVMe into **M2_2** (the second slot). **Do not touch M2_1**, or your GPUs will drop to x8/x4 speeds.
4.  **Cooling:** Ensure the CPU cooler is under **115mm**. The Noctua NH-D9L is a proven choice for 3U builds.
5.  **Software:** Manually set PCIe Link Speed to **"Gen 4"** in BIOS for maximum reliability.

---
**Verification Result:** Confirmed that the i5-12500 supports the `1x16` or `2x8` configuration via the Intel Alder Lake specification. The CX3150X dimensions (3U) perfectly accommodate E-ATX motherboards and the ASUS Turbo 3090's length.
