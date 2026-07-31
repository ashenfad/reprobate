"""Active render-session routing for recursive public helpers."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator

RenderChild = Callable[[object, int], str]
RenderAttrs = Callable[[dict[str, object], str, int], str]


@dataclass(frozen=True)
class RenderSession:
    """Engine callbacks used by public helpers during an active render."""

    render_child: RenderChild
    render_attrs: RenderAttrs


_active_session: ContextVar[RenderSession] = ContextVar("reprobate_render_session")


@contextmanager
def activate_session(session: RenderSession) -> Iterator[None]:
    """Make an engine's recursive callbacks active for the current context."""
    token = _active_session.set(session)
    try:
        yield
    finally:
        _active_session.reset(token)


def get_active_session() -> RenderSession:
    """Return the active render session or raise when no render is in progress."""
    try:
        return _active_session.get()
    except LookupError:
        raise RuntimeError(
            "render_child() must be called within render(). "
            "Use render() as the top-level entry point."
        ) from None
