"""Optional renderer for pydantic models."""

try:
    import pydantic
except ImportError:
    pydantic = None

from .core import render_attrs
from .registry import register

if pydantic is not None:

    @register(pydantic.BaseModel)
    def render_basemodel(obj: "pydantic.BaseModel", budget: int) -> str:
        type_name = type(obj).__name__
        attrs = {name: getattr(obj, name) for name in type(obj).model_fields}
        return render_attrs(attrs, type_name, budget)
