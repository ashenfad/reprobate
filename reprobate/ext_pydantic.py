"""Optional renderer for pydantic models."""

from .core import render_attrs
from .registry import register, register_lazy


def install() -> None:
    """Register the pydantic renderers.

    Run by the registry the first time it meets a pydantic type: an
    object of that type exists, so pydantic is already loaded and the
    import below costs nothing.
    """
    import pydantic

    @register(pydantic.BaseModel)
    def render_basemodel(obj: "pydantic.BaseModel", budget: int) -> str:
        type_name = type(obj).__name__
        attrs = {name: getattr(obj, name) for name in type(obj).model_fields}
        return render_attrs(attrs, type_name, budget)


register_lazy("pydantic", install)
