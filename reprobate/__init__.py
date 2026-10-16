"""reprobate: Budget-controlled repr for Python objects."""

from .core import InferencePolicy, Policy, render, render_attrs, render_child
from .registry import register

__all__ = [
    "InferencePolicy",
    "Policy",
    "register",
    "render",
    "render_attrs",
    "render_child",
]

# Optional type renderers. Each registers itself the first time an object of
# its library's types is rendered, so importing reprobate imports none of them.
from . import (
    ext_arrow,  # noqa: F401
    ext_numpy,  # noqa: F401
    ext_pandas,  # noqa: F401
    ext_pil,  # noqa: F401
    ext_polars,  # noqa: F401
    ext_pydantic,  # noqa: F401
)
