# eGPU Handover Document: RTX 5060 Ti Integration

## Status: ✅ SUCCESS (June 2026)

The eGPU is fully recognized and operational on the host system alongside both internal RTX 3090s.

```text
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 610.43.02              KMD Version: 610.43.02     CUDA UMD Version: 13.3     |
|=========================================+========================+======================|
|   0  NVIDIA GeForce RTX 3090        On  |   00000000:01:00.0 Off |                  N/A |
|=========================================+========================+======================|
|   1  NVIDIA GeForce RTX 3090        On  |   00000000:02:00.0 Off |                  N/A |
|=========================================+========================+======================|
|   2  NVIDIA GeForce RTX 5060 Ti     On  |   00000000:08:00.0 Off |                  N/A |
+-----------------------------------------+------------------------+----------------------+
```

---

## 🛠️ The Final Working Configuration

### 1. BIOS Settings (ASRock Z790 Taichi Lite)
*   **Above 4G Decoding:** Enabled
*   **VT-d / Intel Virtualization:** Disabled (Disables IOMMU/VF allocations system-wide)
*   **SR-IOV Support:** Disabled
*   **CSM:** Disabled
*   **Resizable BAR / C.A.M.:** Disabled (for baseline stability - see ReBAR section below)

### 2. Kernel boot parameters (`/etc/default/grub`)
```text
GRUB_CMDLINE_LINUX_DEFAULT="pci=realloc=off"
```

The currently booted command line may still contain `pci=realloc=off,nosriov` from testing. On kernel `6.8.0-124-generic`, `nosriov` is not a valid PCI option:

```text
PCI: Unknown option `nosriov'
```

It should be removed during cleanup. The working option is `pci=realloc=off`.

---

## 🧠 Diagnostic Explanation (How we solved it)

1.  **BIOS vs Kernel Allocations:** In early boot, the BIOS successfully mapped the eGPU's non-prefetchable `BAR 0` (64 MB) and prefetchable `BAR 1` (256 MB) regions.
2.  **The Trigger:** Later in the boot process, the kernel noticed legacy/unused device resources that weren't fully mapped (such as the GPU's legacy I/O port `BAR 5` or Virtual Function BARs from SR-IOV capability).
3.  **The Fallacy:** Even without `pci=realloc` in GRUB, the kernel's default behavior was to trigger resource reallocation (`pci_bus No. 2 try to assign unassigned res`) to try and fit these unmapped virtual/legacy BARs.
4.  **The Failure:** The reallocation discarded the working BIOS assignments, but then failed to fit the newly requested hotplug allocations (since Thunderbolt bridge windows are constrained to 737 MB by the ACPI map). This left the eGPU with `BAR0 is 0M @ 0x0`.
5.  **The Fix:**
    *   **VT-d disabled** in BIOS may reduce IOMMU-related pressure and should remain part of the known-good baseline unless retested separately.
    *   **`pci=realloc=off`** explicitly commands the Linux kernel not to discard BIOS assignments. The kernel keeps the BIOS-allocated BAR0/BAR1/BAR3 regions and successfully initializes the eGPU.

Confirmed working BAR assignment:

```text
Region 0: Memory at 74000000 (32-bit, non-prefetchable) [size=64M]
Region 1: Memory at 6000000000 (64-bit, prefetchable) [size=256M]
Region 3: Memory at 6010000000 (64-bit, prefetchable) [size=32M]
Region 5: I/O ports at 3000 [size=128]
```

---

## 🚀 Future Options: Testing Resizable BAR

Currently, Resizable BAR (C.A.M.) is disabled, limiting the eGPU's prefetchable memory window to 256 MB. Since we have disabled kernel reallocation (`pci=realloc=off`), we can now attempt to re-enable ReBAR in the BIOS.

### Why it might work now:
When ReBAR is enabled in the BIOS, the ASRock motherboard will allocate a 16 GB prefetchable window above 4 GB for the eGPU at boot time. Because `pci=realloc=off` is set, the kernel will NOT attempt to discard or resize this window.

### How to test:
1.  Reboot into BIOS.
2.  Set **C.A.M. (Clever Access Memory) / Resizable BAR** to **Enabled**.
3.  Boot to Linux.
4.  Run `nvidia-smi` and check if all 3 GPUs load successfully.
5.  If it succeeds, check the BAR sizes using `sudo lspci -vv -s 08:00.0`. `Region 1` should show `size=16G`.
6.  *Fallback:* If the system hangs, gets stuck in a boot loop, or the driver fails again, reboot, enter BIOS, and set Resizable BAR back to **Disabled**.
