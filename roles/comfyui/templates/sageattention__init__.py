import torch
from torch import nn

class SageAttention(nn.Module):
    def __init__(self, *args, **kwargs):
        super().__init__()
    def forward(self, x):
        return x

def sageattn(*args, **kwargs):
    return None

class SageAttentionNode:
    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"tensor": ("TENSOR",)}}
    RETURN_TYPES = ("TENSOR",)
    FUNCTION = "forward"
    CATEGORY = "advanced"

    def forward(self, tensor):
        return (tensor,)

NODE_CLASS_MAPPINGS = {
    "SageAttention": SageAttentionNode
}

print("SageAttention XPU compatibility layer loaded")
