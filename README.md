# README

This is my homelab config. The repo is called `pi` because it started as a single pi. It's now:

- `nameserver-pi` (192.168.50.4) — Pi-hole: DHCP, DNS, ad-blocking
- `homelab-nuc` (192.168.50.5) — Intel NUC running Ubuntu as the main Docker host (Caddy, Home Assistant, media, productivity, LLM tooling, backup Pi-hole)
- `ailab-ubuntu` (192.168.50.10) — bare-metal GPU server: dual RTX 3090 (LLM inference, STT, embeddings, Immich ML) + RTX 5060 Ti eGPU (ComfyUI, Wan2GP, Wolf)
- `ubuntu-8gb-fsn1-1` / Hetzner (Tailnet IP 100.82.91.51) — cloud Docker host for Hermes agents
- `dashserv-m-1` (77.90.42.61) — public VPS baseline host
- `clawd` (192.168.50.12) — additional managed/special-purpose host

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

### Authentication

Authelia provides passkey-based Caddy Forward Auth for services without SSO
and native OpenID Connect for applications such as Linkding and Beszel. The
architecture, decision guide, rollout steps, and recovery paths are documented
in [`docs/authentication.md`](docs/authentication.md).

### Home Assistant

```bash
uv run ansible-playbook setup.yml --tags ha --limit homelab
```

The old `mic_satellites` commands are not currently runnable from the checked-in inventory because that group is not defined.

### AI Lab

```bash
# LLM tools (Open WebUI, LiteLLM, etc.) on homelab-nuc
uv run ansible-playbook setup.yml --tags llm-tools --limit homelab

# LLM inference (LlamaSwap) on ailab-ubuntu
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus

# Observability (Arize Phoenix)
uv run ansible-playbook setup.yml --tags llm-observability --limit homelab

# Everything LLM-related
uv run ansible-playbook setup.yml --tags llm --limit homelab,ailab_ubuntus
```

### LlamaSwap (llama.cpp)

LlamaSwap runs on `ailab-ubuntu` with GPU acceleration across the two RTX 3090s.

- **Primary models:** configured in `group_vars/all/llms.yml` (currently Qwen3.6 35B/27B, Gemma 4 26B/31B, and `qwen3-embedding`)
- **Context sizing:** Qwen and Gemma 4 26B use a 376832-token unified KV pool shared by three concurrent sequences, with requests capped at the native 262144-token model limit. Dense Gemma 4 31B uses a separate 131072-token pool; 262144 leaves GPU0 effectively full and 376832 fails to start while embedding and TTS are resident. These explicit pools preserve headroom for embedding, STT, and TTS services, including TTS's post-JIT CUDA state. Do not rely on llama.cpp `--fit` under tensor parallelism.
- **Prompt caching:** idle histories are selected automatically by prefix similarity and may use up to 8 GiB of host RAM; no fixed llama.cpp slot IDs are assigned. Public `home-*` names map through `model_group_alias`; only the meaningful `-nothink` behavior remains an explicit variant.
- **GPU isolation:** the RTX 5060 Ti is reserved for generative media and gaming. LLM inference and its embedding/STT/TTS companions must continue to fit on the two RTX 3090s.
- **WebUI:** https://llama-swap.kirelabs.org/ui

The controlled Qwen3.6 27B prompt-processing benchmark is documented in
[`docs/qwen36-27b-prompt-processing-benchmark-2026-07-11.md`](docs/qwen36-27b-prompt-processing-benchmark-2026-07-11.md).
Its current recommendation is to retain tensor split, three slots, batch 2048,
and micro-batch 512. Prompt-prefix stability produced a much larger latency
improvement than the tested batch changes. The reserved context-pool size was
held constant during that matrix and still requires a separate benchmark before
any conclusion about changing it.

### Qwen3-TTS Stable Voices

`qwen3-tts` is served by CrispASR as an OpenAI-compatible sibling container
managed by LlamaSwap. It uses Qwen3-TTS 1.7B Base Q8 on GPU1. The stable
`de-host` reference WAV and its exact transcript are mounted from
`crispasr-tts-voices/`; deployment migrates the newest completed `de-host`
reference from the previous faster-qwen3-tts cache.

To replace the voice, update `de-host.wav` and its matching `de-host.txt` on the
host. The text must be the exact spoken content of the reference WAV. CrispASR
uses both files for voice cloning; it does not need the former Python speaker
embedding or VoiceDesign runtime.

```bash
uv run ansible-playbook setup.yml --tags llm-inference --limit ailab_ubuntus
```

Generate speech (`model` must match the LlamaSwap alias `qwen3-tts`):

```bash
curl https://llama-swap.kirelabs.org/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-tts","input":"Hallo, willkommen im Homelab.","voice":"de-host","response_format":"wav"}' \
  --output speech.wav
```

List configured voices (the model query param is required by LlamaSwap's routing):

```bash
curl "https://llama-swap.kirelabs.org/v1/audio/voices?model=qwen3-tts" | jq
```

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

Default STT is Whisper large-v3-turbo Q8 through CrispASR, managed as a
persistent llama-swap sibling on RTX 3090 GPU0. LiteLLM exposes it as
`home-asr`; Wyoming OpenAI calls the canonical
`whisper-large-v3-turbo-q8-crispasr` model through llama-swap. CrispASR also
publishes its native Wyoming STT endpoint on port `10302` for parallel testing;
the existing Wyoming OpenAI gateway remains on port `10300`.

Parakeet was tested as an OpenAI-compatible GPU backend against the previous
Speaches/Faster-Whisper service. It is substantially faster, with a known
quality trade-off for some German technical terms, compound words, and service
names.

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

The historical Parakeet results remain a regression baseline. The deployment
uses CrispASR/Whisper Q8 because real Hermes voice notes showed materially
better German technical-term recognition while still processing about 96x
realtime with a roughly 1.3 GiB process peak.

## LLM Service Architecture

```
Open WebUI → LiteLLM Proxy → LlamaSwap (ailab-ubuntu)
                  ↓
           LiteLLM MCP servers + Google Workspace MCP
                  ↓
           Arize Phoenix [observability]
```

| Service | URL | Host |
| :--- | :--- | :--- |
| Open WebUI | https://open-webui.kirelabs.org | homelab-nuc |
| LiteLLM Admin | https://litellm.kirelabs.org | homelab-nuc |
| Arize Phoenix | https://phoenix.kirelabs.org | homelab-nuc |
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
