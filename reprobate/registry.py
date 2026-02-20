"""Type-specific renderer registry."""

from typing import Any, Callable

Renderer = Callable[[Any, int], str]

_registry: dict[type, Renderer] = {}


def register(cls: type) -> Callable[[Renderer], Renderer]:
    """Register a budget renderer for a type.

    Usage::

        @register(MyClass)
        def render_my_class(obj: MyClass, budget: int) -> str:
            ...
    """

    def decorator(fn: Renderer) -> Renderer:
        _registry[cls] = fn
        return fn

    return decorator


def get_renderer(cls: type) -> Renderer | None:
    """Look up a renderer for a type, checking MRO."""
    for klass in cls.__mro__:
        if klass in _registry:
            return _registry[klass]
    return None
