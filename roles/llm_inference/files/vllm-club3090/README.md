# club-3090 vLLM runtime patches

Vendored from `noonghunna/club-3090` commit
`87ce4b3dd4aa1ef772f5882ea87b95c9183f0450` under Apache-2.0.

The W4A8 patch is active for the Qwen3.8 AutoRound backend. The Mamba and GDN
patches are applied fail-closed to reproduce the tested image state, but remain
runtime-inert while speculative decoding is disabled.

Upstream paths:

- `models/qwen3.6-27b/vllm/patches/w4a8-int8-act`
- `models/qwen3.6-27b/vllm/patches/vllm-pr48375-mamba-drop-eagle-block`
- `models/qwen3.6-27b/vllm/patches/vllm-gdn-mtp-async-spec-order`
