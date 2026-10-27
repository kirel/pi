# NVIDIA P2P trial

Archived experiment from branch `test/nvidia-p2p`, September 29–30, 2026.
These playbooks are invoked explicitly and are not part of the normal deployment.
NVIDIA 615.71.09 with aikitoria revision
`c8bff5400e2fc8bda4cb9a141fb596aad607a35f`; original driver 590.48.01.

To reproduce the experimental installation from the repository root:

```sh
ANSIBLE_VAULT_PASSWORD_FILE=/home/daniel/code/pi/.vault_pass uv run ansible-playbook experiments/nvidia-p2p/run.yml -e p2p_action=apply
```

This saves the original packages, installs matching 615 userspace/firmware,
installs the fork through DKMS, and prepares IOMMU passthrough in GRUB.
It neither stops containers nor reboots nor starts any automatic tests or rollback.
Reboot separately, reconnect here, then check `nvidia-smi`, CUDA P2P on the two
3090s, real LlamaSwap inference, and Wolf. GPU2 remains reserved for media/gaming.

The fork outputs modules in `kernel-open/`, which must be set in DKMS.
Driver packages remain held. Reinstalling the source package replaces the fork;
avoid the ordinary GPU role during the experiment. IOMMU passthrough reduces
DMA isolation. All three GPUs share the driver.

Manual offline recovery on AI Lab (root shell):

Alternatively, prepare the rollback through Ansible with
`uv run ansible-playbook experiments/nvidia-p2p/run.yml -e p2p_action=rollback`
(using the same Vault password file as above). This restores packages and boot
configuration and verifies the module on disk. Reboot separately afterward;
the playbook does not stop containers or reboot the agent's host automatically.

```sh
sudo -i
cp /var/lib/nvidia-p2p-test/debs/*.deb /var/cache/apt/archives/
/var/lib/nvidia-p2p-test/rollback.sh
reboot
```

Both kernel modules and userspace must match. Saved debs must be in APT's archive
cache for `--no-download`. This recovery was successfully executed on 2026-09-29.
The previous NUC controller has been retired. Its logs are retained there under
`/root/nvidia-p2p-controller`; it must not be started again.

## Measured outcome (2026-09-30)

[Benchmark and correctness report](../../docs/qwen38-p2p-benchmark-2026-09-29.md):
NCCL P2P reduced Qwen prefill throughput; SM peer reads returned invalid data,
and Custom All-Reduce returned NaNs. Production config is restored with both
P2P and Custom AR disabled. At the end of testing, the experimental driver
remained installed; the final return to the standard driver was still pending.
The successful recovery mentioned above was an earlier installation-recovery
step, not the final rollback of this experiment.

[Three NCCL tuning tests (September 30)](../../docs/qwen38-p2p-tuning-2026-09-30.md)
confirmed that copy-engine transport and four/eight CTAs do not beat the existing
host-memory path. A further 24-run ACS on/off comparison also left bulk P2P
throughput unchanged at 4.88 GB/s versus 7.78 GB/s with P2P disabled.
All NCCL data checks passed; the separate peer-read and Custom AR failures
remain unresolved. Original ACS settings and the serving configuration were restored.

## Completed rollback (September 30)

The Ansible rollback restored all 19 saved 590.48.01 packages, rebuilt the
modules for kernels 6.8.0-136 and 6.8.0-142, and regenerated GRUB/initramfs.
The experiment's `intel_iommu=on iommu=pt` drop-in was removed. Package holds
were restored after the downgrade and verified for all 19 packages.
After the manual reboot, all three GPUs report the loaded 590.48.01 driver.
The kernel command line retains `pci=realloc=off` without the experiment's
IOMMU arguments. Power limits remain 250 W on each 3090 and 180 W on the 5060 Ti;
all 19 driver package holds remain in place. No Xid or API mismatch was found
in the current boot's kernel log.

Qwen, embedding, ASR and TTS report ready. A real LlamaSwap chat request returned
`42` for `19 + 23`, with NCCL P2P and Custom All-Reduce still disabled.
The reboot changed the 5060 Ti render node from `renderD128` to `renderD130`;
Wolf initially fell back to software encoding. Redeploying the existing Wolf
role resolved the GPU UUID to its current node and recreated the container.
Wolf now reports NVIDIA H.264/H.265/AV1 encoders and a zero-copy pipeline;
a 30-frame 720p NVENC H.264 test succeeded and `/serverinfo` returned status 200.
An actual Moonlight client session was not exercised. Render-node numbering
is still resolved at deployment time, so a future boot that renumbers devices
may require the same scoped redeploy.
