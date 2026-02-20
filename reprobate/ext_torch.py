"""Optional renderer for torch tensors."""

try:
    import torch
except ImportError:
    torch = None

from .core import render_child
from .registry import register

if torch is not None:

    @register(torch.Tensor)
    def render_tensor(obj: "torch.Tensor", budget: int) -> str:
        shape = "x".join(str(d) for d in obj.shape)
        dtype = str(obj.dtype).removeprefix("torch.")
        device = str(obj.device)

        if device == "cpu":
            header = f"Tensor({shape}, {dtype}"
        else:
            header = f"Tensor({shape}, {dtype}, {device}"

        if budget <= len(header) + 1:
            return f"Tensor({shape})"[:budget]

        remaining = budget - len(header) - 2  # ", " before data, ")" at end
        if remaining < 5:
            return (header + ")")[:budget]

        # Peek at flattened values
        flat = obj.detach().cpu().reshape(-1)
        n = flat.numel()
        peek_parts: list[str] = []
        used = 0

        limit = min(n, 20)
        for i in range(limit):
            sep = 2 if peek_parts else 0
            omitted = n - i - 1
            reserve = len(f", ...{omitted} more") if omitted > 0 else 0
            avail = remaining - used - sep - reserve

            r = render_child(flat[i].item(), avail)
            if len(r) > avail or avail < 5:
                break
            peek_parts.append(r)
            used += len(r) + sep

        omitted = n - len(peek_parts)
        if omitted > 0:
            peek_parts.append(f"...{omitted} more")

        return header + ", [" + ", ".join(peek_parts) + "])"
