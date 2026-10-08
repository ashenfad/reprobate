"""Optional renderer for numpy arrays and scalars."""

try:
    import numpy as np
except ImportError:
    np = None

from ._engine.summaries import render_array_summary
from .core import render_child
from .registry import register, register_builtin

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

    def _concrete_integer_types() -> set[type]:
        """numpy's own integer scalar types; user subclasses are excluded.

        ``timedelta64`` subclasses ``signedinteger`` but carries a unit, so it
        has no builtin equivalent.
        """
        found: set[type] = set()
        pending = [np.integer]
        while pending:
            for sub in pending.pop().__subclasses__():
                if sub.__module__ == "numpy" and not issubclass(sub, np.timedelta64):
                    found.add(sub)
                    pending.append(sub)
        return found

    # numpy 2 scalar reprs repeat the dtype (``np.int64(3)``). Scalars with an
    # exact builtin equivalent render as that builtin instead. Extended
    # precision types and datetimes have none and keep their own repr.
    # Conversions match exact types, so every concrete type is listed.
    register_builtin(np.bool_)(bool)
    for _integer in _concrete_integer_types():
        register_builtin(_integer)(int)
    register_builtin(np.float64)(float)
    register_builtin(np.complex128)(complex)
    register_builtin(np.str_)(str)
    register_builtin(np.bytes_)(bytes)

    # Converting a reduced-precision value exactly would expose float64 noise
    # (float32 0.1 is 0.10000000149011612). numpy's str is the shortest text
    # that round-trips at the value's own precision, and parsing it back gives
    # a builtin that spells the same text.
    for _reduced in (np.float16, np.float32):
        register_builtin(_reduced)(lambda value: float(str(value)))
    register_builtin(np.complex64)(lambda value: complex(str(value)))
