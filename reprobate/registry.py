"""Type-specific renderer registry."""

from typing import Any, Callable

Renderer = Callable[[Any, int], str]
Converter = Callable[[Any], object]

_registry: dict[type, Renderer] = {}
_builtin_converters: dict[type, Converter] = {}


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


def register_builtin(cls: type) -> Callable[[Converter], Converter]:
    """Register a conversion from a foreign scalar type to an equivalent builtin.

    The engine renders the converted value in place of the original, so it
    takes part in complete-value probes and uniform collapse like any builtin.
    A renderer registered for the same type takes precedence. The conversion
    applies to exactly this type: a subclass may carry its own repr or state,
    so it is never converted on its ancestor's behalf.
    """

    def decorator(fn: Converter) -> Converter:
        _builtin_converters[cls] = fn
        return fn

    return decorator


def get_builtin_converter(cls: type) -> Converter | None:
    """Look up the builtin conversion registered for exactly this type."""
    return _builtin_converters.get(cls)
