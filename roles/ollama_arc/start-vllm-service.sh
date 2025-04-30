#!/bin/bash
MODEL_PATH=${MODEL_PATH:-"default_model_path"}
SERVED_MODEL_NAME=${SERVED_MODEL_NAME:-"default_model_name"}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-1}

MAX_NUM_SEQS=${MAX_NUM_SEQS:-256}
MAX_NUM_BATCHED_TOKENS=${MAX_NUM_BATCHED_TOKENS:-3000}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-2000}
LOAD_IN_LOW_BIT=${LOAD_IN_LOW_BIT:-"fp8"}
PORT=${PORT:-8000}
VLLM_QUANTIZATION=${VLLM_QUANTIZATION:-""} # Default to empty (no -q argument)
CACHE_DTYPE=${CACHE_DTYPE:-""} # Default to empty (no --kv-cache-dtype argument)

echo "Starting service with model: $MODEL_PATH"
echo "Served model name: $SERVED_MODEL_NAME"
echo "Tensor parallel size: $TENSOR_PARALLEL_SIZE"
echo "Max num sequences: $MAX_NUM_SEQS"
echo "Max num batched tokens: $MAX_NUM_BATCHED_TOKENS"
echo "Max model length: $MAX_MODEL_LEN"
echo "Load in low bit: $LOAD_IN_LOW_BIT"
echo "Port: $PORT"
if [[ -n "$VLLM_QUANTIZATION" ]]; then
  echo "Quantization method: $VLLM_QUANTIZATION"
else
  echo "Quantization method: Not specified (default)"
fi
if [[ -n "$CACHE_DTYPE" ]]; then
  echo "KV Cache DType: $CACHE_DTYPE"
else
  echo "KV Cache DType: Not specified (default)"
fi

export CCL_WORKER_COUNT=2
export SYCL_CACHE_PERSISTENT=1
export FI_PROVIDER=shm
export CCL_ATL_TRANSPORT=ofi
export CCL_ZE_IPC_EXCHANGE=sockets
export CCL_ATL_SHM=1

export USE_XETLA=OFF
export SYCL_PI_LEVEL_ZERO_USE_IMMEDIATE_COMMANDLISTS=2
export TORCH_LLM_ALLREDUCE=0

export CCL_SAME_STREAM=1
export CCL_BLOCKING_WAIT=0

source /opt/intel/1ccl-wks/setvars.sh

# Build the command arguments dynamically
CMD_ARGS=(
  --served-model-name "$SERVED_MODEL_NAME"
  --port "$PORT"
  --model "$MODEL_PATH"
  --trust-remote-code
  --block-size 8
  --gpu-memory-utilization 0.95
  --device xpu
  --dtype float16
  --enforce-eager
  --load-in-low-bit "$LOAD_IN_LOW_BIT"
  --max-model-len "$MAX_MODEL_LEN"
  --max-num-batched-tokens "$MAX_NUM_BATCHED_TOKENS"
  --max-num-seqs "$MAX_NUM_SEQS"
  --tensor-parallel-size "$TENSOR_PARALLEL_SIZE"
  --disable-async-output-proc
  --distributed-executor-backend ray
  --download-dir /llm/models # AI! make configurable via env var
  --enable-prefix-caching
)

# Conditionally add the quantization argument if VLLM_QUANTIZATION is set and not empty
if [[ -n "$VLLM_QUANTIZATION" ]]; then
  CMD_ARGS+=(-q "$VLLM_QUANTIZATION")
fi

# Conditionally add the kv cache dtype argument if CACHE_DTYPE is set and not empty
if [[ -n "$CACHE_DTYPE" ]]; then
  CMD_ARGS+=(--kv-cache-dtype "$CACHE_DTYPE")
fi

# Execute the command
python -m ipex_llm.vllm.xpu.entrypoints.openai.api_server "${CMD_ARGS[@]}"
