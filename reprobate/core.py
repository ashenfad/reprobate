"""Stable public facade for the rendering engine."""

from ._engine import InferencePolicy, Policy
from ._engine import render as _render
from ._engine import render_attrs as _render_attrs
from ._session import get_active_session


def render(
    obj: object,
    budget: int = 200,
    policy: Policy = "greedy",
    *,
    inference: InferencePolicy = "best_effort",
) -> str:
    """Render an object through the rendering engine."""
    return _render(obj, budget, policy, inference=inference)


def render_child(obj: object, budget: int) -> str:
    """Render a child through the engine that owns the active render session."""
    return get_active_session().render_child(obj, budget)


def render_attrs(attrs: dict[str, object], type_name: str, budget: int) -> str:
    """Render object attributes through the active engine.

    Outside an active render, create a standalone engine session for compatibility.
    """
    try:
        session = get_active_session()
    except RuntimeError:
        return _render_attrs(attrs, type_name, budget)
    return session.render_attrs(attrs, type_name, budget)
