"""reprobate: Budget-controlled repr for Python objects."""

from .core import Policy, render, render_attrs, render_child
from .registry import register

__all__ = [
    "Policy",
    "register",
    "render",
    "render_attrs",
    "render_child",
]

# Auto-register optional type renderers when their deps are available.
from . import (
    ext_arrow,  # noqa: F401
    ext_numpy,  # noqa: F401
    ext_pandas,  # noqa: F401
    ext_pil,  # noqa: F401
    ext_polars,  # noqa: F401
    ext_pydantic,  # noqa: F401
)
