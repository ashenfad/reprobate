"""Type-specific renderer registry."""

import threading
from typing import Any, Callable

Renderer = Callable[[Any, int], str]
Converter = Callable[[Any], object]

_registry: dict[type, Renderer] = {}
_builtin_converters: dict[type, Converter] = {}
_lazy: dict[str, Callable[[], None]] = {}
# Installs run one at a time, and a package stays pending until its install
# has finished: a lookup that arrives meanwhile waits rather than finding
# neither the installer nor its renderers. Reentrant, and the package marked
# in progress, because an install registers renderers, and registering runs
# pending installs first.
_install_lock = threading.RLock()
_installing: set[str] = set()


def register(cls: type) -> Callable[[Renderer], Renderer]:
    """Register a budget renderer for a type.

    Usage::

        @register(MyClass)
        def render_my_class(obj: MyClass, budget: int) -> str:
            ...
    """

    def decorator(fn: Renderer) -> Renderer:
        # the library's own renderers go in first, so this one replaces
        # them rather than being replaced when they arrive
        if _lazy:
            _install_for(cls)
        _registry[cls] = fn
        return fn

    return decorator


def register_lazy(package: str, install: Callable[[], None]) -> None:
    """Defer a library's registrations until they can matter.

    ``install`` registers the renderers for the types of ``package`` (a
    top-level package name). It runs the first time a lookup meets a type
    defined in that package, anywhere in the type's MRO, and never before:
    an object of the type exists by then, so the package is already loaded
    and ``install`` imports nothing new. Importing reprobate therefore
    imports none of the libraries it can render.
    """
    _lazy[package] = install


def _install_for(cls: type) -> None:
    """Run the deferred registrations for the packages ``cls`` comes from."""
    with _install_lock:
        for klass in cls.__mro__:
            package = (getattr(klass, "__module__", None) or "").partition(".")[0]
            install = _lazy.get(package)
            if install is None or package in _installing:
                continue
            _installing.add(package)
            try:
                install()
            except Exception:
                pass  # no renderers for that library: render it generically
            finally:
                _installing.discard(package)
                _lazy.pop(package, None)


def get_renderer(cls: type) -> Renderer | None:
    """Look up a renderer for a type, checking MRO."""
    if _lazy:
        _install_for(cls)
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
        if _lazy:
            _install_for(cls)
        _builtin_converters[cls] = fn
        return fn

    return decorator


def get_builtin_converter(cls: type) -> Converter | None:
    """Look up the builtin conversion registered for exactly this type."""
    if _lazy:
        _install_for(cls)
    return _builtin_converters.get(cls)
