"""Optional renderer for numpy arrays."""

try:
    import numpy as np
except ImportError:
    np = None

from ._engine.summaries import render_array_summary
from .core import render_child
from .registry import register

if np is not None:

    @register(np.ndarray)
    def render_ndarray(obj: "np.ndarray", budget: int) -> str:
        flat = obj.flat
        return render_array_summary(
            "ndarray",
            obj.shape,
            str(obj.dtype),
            obj.size,
            budget,
            render_child,
            value_at=flat.__getitem__,
        )
