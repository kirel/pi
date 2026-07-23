# eGPU Stability Plan (RTX 5060 Ti on ASRock Z790 Taichi Lite)

## Current diagnosis

The eGPU is the current stability risk, not the resident ASR service or the
3090 VRAM layout.
Kernel logs showed the RTX 5060 Ti at PCI `0000:08:00.0` / UUID
`GPU-070fdafb-63c8-9e3e-635e-9c29ba36f82f` triggering:

```text
NVRM: Xid (PCI:0000:08:00): 31 ... MMU Fault ... ACCESS_TYPE_VIRT_READ
nvGpuOpsReportFatalError: uvm encountered global fatal error 0x60, requiring os reboot to recover
Xid ... 154 ... GPU recovery action ... OS Reboot
```

Once this happens, NVIDIA UVM is poisoned globally: existing CUDA contexts may keep
running for a while, but new large CUDA loads fail (llama-swap reloads and
temporary Parakeet migration tests). A normal container restart is not enough; host reboot/power-cycle is
required.

Ghost VRAM on GPU2 is not itself evidence of a leak here; it can simply be ComfyUI
models still resident.

## Immediate software mitigations

1. Keep Parakeet resident through llama-swap:

```yaml
llamaswap_preload:
  - parakeet-tdt-0.6b
```

This avoids repeated ONNX Runtime CUDA initialization. The durable target is
GPU0; the RTX 5060 Ti is only used temporarily during migration.

2. Move off the bleeding-edge 610 driver branch. Pin NVIDIA through the `gpu` role
to a packaged, less experimental branch first:

```yaml
nvidia_driver_version: 590.48.01-0ubuntu1
```

If 590 still Xids, try `580.167.08-1ubuntu1`. If 580 does not support the 5060 Ti
well enough, go back to the newest non-610 branch available.

3. Add conservative NVIDIA module options through the `gpu` role:

```text
options nvidia NVreg_PreserveVideoMemoryAllocations=1 NVreg_DynamicPowerManagement=0x02
```

The goal is to reduce aggressive power-state transitions on the Thunderbolt/eGPU
path.

## BIOS settings to verify

Motherboard: ASRock Z790 Taichi Lite, BIOS 12.01.

Recommended stability baseline:

- Above 4G Decoding: Enabled
- CSM: Disabled
- VT-d / IOMMU: keep the known-good setting from the original eGPU bring-up
- SR-IOV: Disabled
- PCIe ASPM / Native ASPM / PCIe Native Power Management: Disabled
- Thunderbolt PCIe tunneling: Enabled
- Thunderbolt Security: No Security or User Authorization
- Thunderbolt boot/preboot support: Disabled unless needed
- Wake from Thunderbolt/USB: Disabled
- ErP / deep sleep: Disabled
- Re-Size BAR / C.A.M.: keep Disabled for baseline stability; test Enabled only
  after the driver is stable

Known-good Linux boot parameter from bring-up:

```text
pci=realloc=off
```

Keep this unless deliberately retesting PCI resource allocation.

## Validation after reboot

1. Confirm all GPUs:

```bash
nvidia-smi -L
nvidia-smi --query-gpu=index,uuid,name,memory.used,memory.free --format=csv
```

2. Confirm no fresh kernel errors:

```bash
sudo dmesg -T | grep -Ei 'NVRM|Xid|thunderbolt|AER|pcie' | tail -100
```

3. Load stable baseline:

- 27B or 35B via llama-swap
- qwen3-embedding on GPU0
- Parakeet STT on GPU0

4. Test Parakeet once through llama-swap and keep it resident:

```bash
curl -F file=@sample.ogg -F model=parakeet-tdt-0.6b \
  http://127.0.0.1:9292/v1/audio/transcriptions
```

5. Only then start ComfyUI/Wan2GP workloads on GPU2. If Xid 31 returns, isolate the
eGPU workload and test with ReBAR off, ASPM off, and driver branch 590 vs 580.
