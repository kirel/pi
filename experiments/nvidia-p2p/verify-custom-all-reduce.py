"""Check installed vLLM CustomAllreduce, including its CUDA graph path."""
import os
import torch
import torch.distributed as dist
from vllm.distributed.device_communicators.custom_all_reduce import CustomAllreduce
rank = int(os.environ['LOCAL_RANK'])
torch.cuda.set_device(rank)
dist.init_process_group('gloo')
ar = CustomAllreduce(dist.group.WORLD, rank)
assert not ar.disabled, 'Custom all-reduce not enabled'
failures = 0
for dtype in (torch.float32, torch.bfloat16):
    x = torch.full((1024,), rank + 1, device=f'cuda:{rank}', dtype=dtype)
    for graph in (False, True):
        if graph:
            g = torch.cuda.CUDAGraph()
            with ar.capture():
                with torch.cuda.graph(g):
                    y = ar.custom_all_reduce(x)
            g.replay()
        else:
            y = ar.custom_all_reduce(x)
        torch.cuda.synchronize()
        assert y is not None
        wrong = (y != 3).sum().item()
        print(f'rank={rank} dtype={dtype} graph={graph} mismatches={wrong} first={y[0].item()}', flush=True)
        failures += wrong != 0
ar.close()
dist.destroy_process_group()
assert failures == 0, f'{failures} incorrect reductions'
