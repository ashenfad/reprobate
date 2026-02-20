"""Optional renderer for numpy arrays."""

try:
    import numpy as np
except ImportError:
    np = None

from .core import render_child
from .registry import register

if np is not None:

    @register(np.ndarray)
    def render_ndarray(obj: "np.ndarray", budget: int) -> str:
        shape = "x".join(str(d) for d in obj.shape)
        dtype = str(obj.dtype)
        header = f"ndarray({shape}, {dtype}"

        # header + ")" is the minimum useful output
        if budget <= len(header) + 1:
            return f"ndarray({shape})"[:budget]

        remaining = budget - len(header) - 2  # ", " before data, ")" at end
        if remaining < 5:
            return (header + ")")[:budget]

        # Peek at flattened values
        flat = obj.flat
        n = obj.size
        peek_parts: list[str] = []
        used = 0

        limit = min(n, 20)
        for i in range(limit):
            sep = 2 if peek_parts else 0  # ", "
            omitted = n - i - 1
            reserve = len(f", ...{omitted} more") if omitted > 0 else 0
            avail = remaining - used - sep - reserve

            r = render_child(flat[i], avail)
            if len(r) > avail or avail < 5:
                break
            peek_parts.append(r)
            used += len(r) + sep

        omitted = n - len(peek_parts)
        if omitted > 0:
            peek_parts.append(f"...{omitted} more")

        return header + ", [" + ", ".join(peek_parts) + "])"
