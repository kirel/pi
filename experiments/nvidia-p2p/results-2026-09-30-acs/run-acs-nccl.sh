#!/bin/bash
set -euo pipefail
[[ $# == 3 && "$1" =~ ^[01]$ && "$2" =~ ^[01]$ && "$3" =~ ^[01]$ ]] || exit 2
original0=$(setpci -s 00:01.0 ECAP_ACS+6.w)
original1=$(setpci -s 00:01.1 ECAP_ACS+6.w)
restore() {
 setpci -s 00:01.0 ECAP_ACS+6.w="$original0"
 setpci -s 00:01.1 ECAP_ACS+6.w="$original1"
 echo "Restored ACS: $(setpci -s 00:01.0 ECAP_ACS+6.w) $(setpci -s 00:01.1 ECAP_ACS+6.w)"
}
trap restore EXIT
trap 'exit 130' INT TERM HUP
[[ "$original0" == 001d && "$original1" == 001d ]] || exit 2
if [[ "$2" == 0 ]]; then
 setpci -s 00:01.0 ECAP_ACS+6.w=0000
 setpci -s 00:01.1 ECAP_ACS+6.w=0000
fi
echo "Active ACS: $(setpci -s 00:01.0 ECAP_ACS+6.w) $(setpci -s 00:01.1 ECAP_ACS+6.w)"
nvidia-smi -i 0,1 --query-gpu=index,temperature.gpu,clocks_throttle_reasons.sw_thermal_slowdown,power.limit --format=csv
docker exec -e NCCL_P2P_DISABLE="$1" -e NCCL_CUMEM_ENABLE=0 -e NCCL_P2P_LEVEL=PHB \
 -e NCCL_P2P_READ_ENABLE=0 -e NCCL_P2P_DIRECT_DISABLE=1 -e NCCL_DEBUG=INFO \
 -e NCCL_DEBUG_SUBSYS=INIT,GRAPH,P2P,SHM,NET \
 -e LD_LIBRARY_PATH=/usr/local/lib/python3.12/dist-packages/nvidia/nccl/lib \
 Qwen3.8-27B-Instruct-AutoRound-vLLM timeout -k 5 60 /tmp/nccl-tests/build/all_reduce_perf \
 -b 4K -e 64M -f 4 -g 2 -w 10 -n 100 -c 1 -G "$3"
