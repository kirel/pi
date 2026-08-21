#!/usr/bin/env bash
set -euo pipefail

# These anchor-checked patches modify only the ephemeral vLLM container. The
# W4A8 installer refuses to boot when int8 activations were requested but the
# pinned vLLM source no longer matches its expected anchors.
bash /etc/club3090/w4a8/install.sh
bash /etc/club3090/pr48375/install.sh
bash /etc/club3090/gdn-async-order/install.sh

exec vllm serve "$@"
