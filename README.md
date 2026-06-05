# README

This is my homelab config. The repo is called `pi` because it started as a single pi. It's now:

- `nameserver-pi` (192.168.50.4) — Pi-hole: DHCP, DNS, ad-blocking
- `homelab-nuc` (192.168.50.5) — Intel NUC running Ubuntu as a Docker host (all services are containers, inc. a Pi-hole backup)
- `ailab-proxmox` (192.168.50.9) — Proxmox hypervisor
- `ailab-ubuntu` (192.168.50.10) — GPU server (RTX 3090) for LLM inference and image generation

## Bootstrap the Pi

1. Download the pi imager at https://www.raspberrypi.com/software/
2. Select Pi OS Lite 64 bit
3. Set hostname to pihole.local
4. Activate SSH, and paste your public key into the SSH key field
5. Set language settings to Berlin timezone and us keyboard
6. Write the image
7. Eject and reinsert the memory card

```bash
uv run ansible-playbook prep_pi.yml
```

## Setup

### Basic Setup

```bash
# Install dependencies using uv
uv pip sync
# Install Ansible Galaxy roles
uv run ansible-galaxy install --force-with-deps -r requirements.yml
```

### Everything

```bash
uv run ansible-playbook setup.yml
```

### DNS, Proxy, Dashboard

```bash
uv run ansible-playbook setup.yml --tags caddy,pihole,homepage --limit homelab,nameserver
```

### Home Assistant

```bash
uv run ansible-playbook setup.yml --tags ha
uv run ansible-playbook setup.yml --limit mic_satellites -t satellite-audio
uv run ansible-playbook setup.yml --limit mic_satellites -t wyoming --start-at-task="Start wyoming stack"
```

### AI Lab

```bash
# LLM tools (Open WebUI, LiteLLM, etc.) on homelab-nuc
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab

# LLM inference (LlamaSwap) on ailab-ubuntu
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus

# Observability (Langfuse)
uv run ansible-playbook setup.yml --tags llm-observability --limit homelab

# Everything LLM-related
uv run ansible-playbook setup.yml --tags llm --limit homelab,ailab_ubuntus
```

### LlamaSwap (llama.cpp)

LlamaSwap runs on `ailab-ubuntu` with GPU acceleration (RTX 3090 24GB).

- **Model:** Qwen3-VL-8B-Instruct-GGUF Q8_K_XL from Unsloth
- **Context Size:** 92,375 tokens max (92,500+ causes OOM)
- **WebUI:** https://llama-swap.kirelabs.org/ui

### Embedding Presets

Embedding models use a simple fixed default in `group_vars/all/llms.yml`:

- `ctx-size 4096`
- `batch-size 1024`
- `ubatch-size 1024`

This fits typical memory-search chunks around a few hundred tokens without
reserving long-document KV/cache by default.

Why these defaults:

- For memory-search style chunks around 400 tokens, embedding quality does not improve from oversized context or batch settings as long as the chunk fits.
- `--ctx-size` mainly controls how much input can fit before truncation and how much KV cache is reserved.
- `--batch-size` affects prompt-processing throughput and workspace allocation, not embedding quality.
- In this `llama.cpp` build, embeddings clamp `n_batch` down to `n_ubatch` if `n_batch > n_ubatch`, so setting only a huge `--batch-size` does not provide the expected benefit.

If you need variants, the practical fallbacks are:

- lower memory: `2048 / 512 / 512`
- longer documents: `8192 / 2048 / 2048`

After changing the values, redeploy `llm-inference`.

### Benchmarking

Compare end-to-end latency (TTFT) and throughput (TPS) across models:

```bash
LITELLM_MASTER_KEY=<your-key> uv run --with openai python3 todo/scripts/llm_benchmark.py
```

### STT for LLM Agents

Default STT should stay on Speaches with `Systran/faster-whisper-large-v3`.

Parakeet TDT 0.6B v3 GPU was tested as an OpenAI-compatible ad-hoc
container on `ailab-ubuntu` against Speaches. The Parakeet GPU path is much
faster, but less reliable for German agent input, especially technical terms,
compound words, and service names. For agent transcription, those errors are
more risky than raw WER suggests because they can change tool names, service
names, or user intent.

Benchmark notes from the 2026-06-04 test run:

- English JFK smoke test: both Speaches and Parakeet v3 reached WER `0.000`.
- German synthetic TTS smoke test: Speaches reached WER `0.000`; Parakeet v3
  produced errors such as `Spracherkennungsdist` and `Hohenla`.
- German multi-sample test: 7 Speaches-generated samples, 10.7s to 61.4s,
  233.4s total audio.
- German accuracy: Speaches `large-v3` WER macro `4.8%`, weighted WER `3.4%`,
  CER macro `1.4%`.
- German accuracy: Parakeet v3 GPU WER macro `7.3%`, weighted WER `6.2%`,
  CER macro `1.8%`.
- German speed: Speaches processed the sample set in `9.23s` (`25.3x`
  realtime); Parakeet v3 GPU processed it in `1.35s` (`172.4x` realtime).
- Parallel throughput on the 11s JFK sample: Speaches stayed around `18x`
  realtime at concurrency 16; Parakeet v3 GPU reached about `157x` realtime at
  concurrency 16.

Recommendation: use Speaches `large-v3` as the default for agent-facing STT.
Only consider Parakeet v3 GPU as a separate fast path for high-volume,
low-risk transcription where occasional German technical-word mistakes are
acceptable.

## LLM Service Architecture

```
Open WebUI → LiteLLM Proxy → LlamaSwap (ailab-ubuntu)
                  ↓
           MCP-Proxy + Google Workspace MCP
                  ↓
           Langfuse [observability]
```

| Service | URL | Host |
| :--- | :--- | :--- |
| Open WebUI | https://open-webui.kirelabs.org | homelab-nuc |
| LiteLLM Admin | https://litellm-ui.kirelabs.org | homelab-nuc |
| Langfuse | https://langfuse.kirelabs.org | homelab-nuc |
| LlamaSwap | https://llama-swap.kirelabs.org | ailab-ubuntu |
| ComfyUI | https://comfyui.kirelabs.org | ailab-ubuntu |

## Secrets

```bash
uv run ansible-vault edit group_vars/all/secrets.yml
```

## Manual router setup

1. Turn DHCP off. Pi-hole and pihole-homelab take over.

## Troubleshooting

### Fix bluetooth

```bash
uv run ansible-playbook fix_hass_bluetooth.yml
```

### Ring-MQTT token expired

```bash
ssh root@homelab-nuc.lan
HOST_PATH=/home/nuc/config/ring-mqtt/
docker run -it --rm --mount type=bind,source=$HOST_PATH,target=/data --entrypoint /app/ring-mqtt/init-ring-mqtt.js tsightler/ring-mqtt
docker restart ring-mqtt
```
