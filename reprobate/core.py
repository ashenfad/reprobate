"""Stable public facade for the active rendering engine."""

from . import _legacy
from ._session import RenderSession, activate_session, get_active_session

Policy = _legacy.Policy

_LEGACY_SESSION = RenderSession(
    render_child=_legacy.render_child,
    render_attrs=_legacy.render_attrs,
)


def render(obj: object, budget: int = 200, policy: Policy = "greedy") -> str:
    """Render an object through the active legacy-compatible engine."""
    with activate_session(_LEGACY_SESSION):
        return _legacy.render(obj, budget, policy)


def render_child(obj: object, budget: int) -> str:
    """Render a child through the engine that owns the active render session."""
    return get_active_session().render_child(obj, budget)


def render_attrs(attrs: dict[str, object], type_name: str, budget: int) -> str:
    """Render object attributes through the active engine.

    Outside an active render, retain the legacy helper's behavior for compatibility.
    """
    try:
        session = get_active_session()
    except RuntimeError:
        return _legacy.render_attrs(attrs, type_name, budget)
    return session.render_attrs(attrs, type_name, budget)
