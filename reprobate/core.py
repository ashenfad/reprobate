"""Core rendering engine: recursive budget-allocated repr."""

import collections
import contextvars
import dataclasses
from typing import Literal

from .registry import get_renderer

MIN_BUDGET = 5
MIN_CHILD_BUDGET = 15

PROTOCOL_METHOD = "__budget_repr__"

Policy = Literal["greedy", "even"]
_policy: contextvars.ContextVar[Policy] = contextvars.ContextVar(
    "budget_policy", default="greedy"
)
_seen: contextvars.ContextVar[set[int]] = contextvars.ContextVar("seen")

CIRCULAR = "<...>"


def render(obj: object, budget: int = 200, policy: Policy = "greedy") -> str:
    """Render a Python object within a character budget.

    Priority order:
    1. ``__budget_repr__`` protocol method on the object
    2. Type-specific renderer from the registry
    3. Generic fallback (primitives, containers, attribute decomposition)

    Args:
        obj: Any Python object.
        budget: Maximum characters in the output.
        policy: Budget allocation for object attributes.
            ``"greedy"`` (default) gives each attr as much budget as
            remains — first attrs get the most detail.
            ``"even"`` divides budget equally across attrs so all
            fields get comparable detail.

    Returns:
        A string of length <= budget representing the object.
    """
    policy_token = _policy.set(policy)
    seen_token = _seen.set(set())
    try:
        return render_child(obj, budget)
    finally:
        _seen.reset(seen_token)
        _policy.reset(policy_token)


def render_child(obj: object, budget: int) -> str:
    """Render a child object within an ongoing render call.

    Use this instead of ``render()`` inside custom renderers to avoid
    resetting the policy and cycle-detection state.
    """
    if budget < MIN_BUDGET:
        return "..."[:budget]

    # Cycle detection for mutable containers/objects.
    # Primitives (None, bool, int, float, str, bytes) are immutable
    # and can't form cycles, so we skip them.
    if not isinstance(obj, (type(None), bool, int, float, str, bytes)):
        try:
            seen = _seen.get()
        except LookupError:
            raise RuntimeError(
                "render_child() must be called within render(). "
                "Use render() as the top-level entry point."
            ) from None
        obj_id = id(obj)
        if obj_id in seen:
            return CIRCULAR[:budget]
        seen.add(obj_id)
        try:
            return _render_inner(obj, budget)
        finally:
            seen.discard(obj_id)

    return _render_inner(obj, budget)


def _render_inner(obj: object, budget: int) -> str:
    """Dispatch to protocol, registry, or generic fallback."""
    # 1. Protocol method
    method = getattr(type(obj), PROTOCOL_METHOD, None)
    if method is not None:
        return method(obj, budget)[:budget]

    # 2. Registry
    renderer = get_renderer(type(obj))
    if renderer is not None:
        return renderer(obj, budget)[:budget]

    # 3. Generic fallback
    return _render_generic(obj, budget)


def _render_generic(obj: object, budget: int) -> str:
    """Fallback renderer for unregistered types."""
    if obj is None or isinstance(obj, (bool, int, float)):
        return _render_primitive(obj, budget)

    if isinstance(obj, str):
        return _render_str(obj, budget)

    if isinstance(obj, bytes):
        return _render_bytes(obj, budget)

    if isinstance(obj, collections.defaultdict):
        return _render_defaultdict(obj, budget)

    if isinstance(obj, collections.Counter):
        return _render_counter(obj, budget)

    if isinstance(obj, dict):
        return _render_dict(obj, budget)

    # namedtuple before plain tuple
    if isinstance(obj, tuple) and hasattr(type(obj), "_fields"):
        return _render_namedtuple(obj, budget)

    if isinstance(obj, (list, tuple)):
        return _render_sequence(obj, budget)

    if isinstance(obj, (set, frozenset)):
        return _render_set(obj, budget)

    if isinstance(obj, collections.deque):
        return _render_deque(obj, budget)

    return _render_object(obj, budget)


def _render_primitive(obj: object, budget: int) -> str:
    r = repr(obj)
    if len(r) <= budget:
        return r
    return r[: budget - 1] + "\u2026"


def _render_str(obj: str, budget: int) -> str:
    r = repr(obj)
    if len(r) <= budget:
        return r
    # budget must fit: opening quote + chars + ... + closing quote = 1 + inner + 3 + 1
    if budget < 6:
        return r[:budget]
    quote = r[0]
    inner = budget - 5  # quote(1) + chars(inner) + ...(3) + quote(1)
    return f"{quote}{obj[:inner]}...{quote}"


def _render_bytes(obj: bytes, budget: int) -> str:
    r = repr(obj)
    if len(r) <= budget:
        return r
    if budget < 6:
        return r[:budget]
    inner = budget - 5  # b' + chars + ... + '
    return f"b'{obj[:inner].decode('ascii', errors='replace')}...'"


def _render_dict(obj: dict, budget: int) -> str:
    if not obj:
        return "{}"
    n = len(obj)
    tag = f"{{...{n} items}}"
    if budget < len(tag):
        return ("{...}"[:budget]) if budget >= 2 else "{"[:budget]
    if budget <= len(tag):
        return tag

    remaining = budget - 2  # { and }
    parts: list[str] = []
    shown = 0

    for key, value in obj.items():
        sep_cost = 2 if parts else 0  # ", "
        omitted = n - shown
        reserve = len(f", ...{omitted - 1} more") if omitted > 1 else 0
        available = remaining - sep_cost - reserve

        key_r = render_child(key, min(available // 2, 40))
        prefix = f"{key_r}: "
        val_budget = available - len(prefix)

        if val_budget < MIN_CHILD_BUDGET:
            break

        val_r = render_child(value, val_budget)
        part = f"{prefix}{val_r}"
        parts.append(part)
        remaining -= len(part) + sep_cost
        shown += 1

    omitted = n - shown
    if omitted > 0:
        parts.append(f"...{omitted} more")

    return "{" + ", ".join(parts) + "}"


def _render_sequence(obj: list | tuple | collections.deque, budget: int) -> str:
    open_b, close_b = ("(", ")") if isinstance(obj, tuple) else ("[", "]")
    if not obj:
        return open_b + close_b
    n = len(obj)

    tag = f"{open_b}...{n} items{close_b}"
    if budget <= len(tag):
        return tag[:budget]

    remaining = budget - 2  # brackets
    head_parts: list[str] = []
    tail_parts: list[str] = []

    # Head items
    head_idx = 0
    while head_idx < n:
        sep_cost = 2 if head_parts else 0
        omitted = n - head_idx - len(tail_parts)
        reserve = len(f", ...{omitted - 1} more") if omitted > 1 else 0
        available = remaining - sep_cost - reserve

        if available < MIN_CHILD_BUDGET:
            break

        part = render_child(obj[head_idx], available)
        head_parts.append(part)
        remaining -= len(part) + sep_cost
        head_idx += 1

    # Tail item if budget allows and we skipped items
    omitted = n - head_idx
    if omitted > 1 and remaining > MIN_CHILD_BUDGET + 15:
        tail_budget = min(remaining - len(f", ...{omitted - 1} more, "), remaining // 3)
        if tail_budget >= MIN_CHILD_BUDGET:
            tail_r = render_child(obj[-1], tail_budget)
            tail_parts.append(tail_r)
            remaining -= len(tail_r) + 2
            omitted -= 1

    mid = f"...{omitted} more" if omitted > 0 else None
    all_parts = head_parts + ([mid] if mid else []) + tail_parts
    return open_b + ", ".join(all_parts) + close_b


def _render_set(obj: set | frozenset, budget: int) -> str:
    prefix = "frozenset(" if isinstance(obj, frozenset) else ""
    suffix = ")" if isinstance(obj, frozenset) else ""
    open_b = prefix + "{"
    close_b = "}" + suffix

    if not obj:
        if isinstance(obj, frozenset):
            return ("frozenset()")[:budget]
        return "set()"[:budget]

    n = len(obj)
    tag = f"{open_b}...{n} items{close_b}"
    if budget <= len(tag):
        return tag[:budget]

    remaining = budget - len(open_b) - len(close_b)
    parts: list[str] = []
    shown = 0

    for item in obj:
        sep_cost = 2 if parts else 0
        omitted = n - shown
        reserve = len(f", ...{omitted - 1} more") if omitted > 1 else 0
        available = remaining - sep_cost - reserve

        if available < MIN_CHILD_BUDGET:
            break

        part = render_child(item, available)
        parts.append(part)
        remaining -= len(part) + sep_cost
        shown += 1

    omitted = n - shown
    if omitted > 0:
        parts.append(f"...{omitted} more")

    return open_b + ", ".join(parts) + close_b


def _type_stub(val: object) -> str:
    """Minimal type representation: <type> or <type(len)> for sized types."""
    type_name = type(val).__name__
    if hasattr(val, "__len__"):
        try:
            return f"<{type_name}({len(val)})>"
        except Exception:
            pass
    return f"<{type_name}>"


def render_attrs(attrs: dict[str, object], type_name: str, budget: int) -> str:
    """Render as TypeName(key=val, ...) with three-phase budget degradation.

    Phase 1: Full render of values (greedy).
    Phase 2: Stub remaining attrs as name=<type> or name=<type(len)>.
    Phase 3: Count any remaining as ...N more.
    """
    tag = f"<{type_name}>"
    n = len(attrs)

    if not attrs:
        return tag[:budget]

    shell = f"{type_name}()"
    if budget <= len(shell):
        return tag[:budget]

    remaining = budget - len(type_name) - 2  # Name( and )
    parts: list[str] = []
    attr_items = list(attrs.items())
    idx = 0
    even = _policy.get() == "even"

    # Phase 1: Full render
    while idx < n:
        sep_cost = 2 if parts else 0
        rest = n - idx
        reserve = len(f", ...{rest - 1} more") if rest > 1 else 0
        available = remaining - sep_cost - reserve

        if even and rest > 1:
            # Equal share of remaining budget per unrendered attr,
            # accounting for separators between them.
            per_attr = (remaining - (rest - 1) * 2) // rest
            available = min(available, per_attr)

        prefix = f"{attr_items[idx][0]}="
        val_budget = available - len(prefix)

        if val_budget < MIN_CHILD_BUDGET:
            break

        val_r = render_child(attr_items[idx][1], val_budget)
        part = f"{prefix}{val_r}"
        parts.append(part)
        remaining -= len(part) + sep_cost
        idx += 1

    # Phase 2: Stub remaining with type info
    while idx < n:
        attr_name, attr_val = attr_items[idx]
        stub = _type_stub(attr_val)
        part = f"{attr_name}={stub}"
        sep_cost = 2 if parts else 0
        rest = n - idx - 1
        reserve = len(f", ...{rest} more") if rest > 0 else 0

        if len(part) + sep_cost + reserve > remaining:
            break

        parts.append(part)
        remaining -= len(part) + sep_cost
        idx += 1

    # Phase 3: Count remaining
    omitted = n - idx
    if omitted > 0:
        parts.append(f"...{omitted} more")

    result = f"{type_name}(" + ", ".join(parts) + ")"
    if len(result) > budget:
        return tag[:budget]
    return result


def _render_namedtuple(obj: tuple, budget: int) -> str:
    type_name = type(obj).__name__
    fields = type(obj)._fields
    attrs = dict(zip(fields, obj))
    return render_attrs(attrs, type_name, budget)


def _render_defaultdict(obj: collections.defaultdict, budget: int) -> str:
    factory = obj.default_factory
    factory_name = factory.__name__ if factory is not None else "None"
    prefix = f"defaultdict({factory_name}, "
    suffix = ")"

    shell = f"defaultdict({factory_name})"
    if budget <= len(shell):
        return shell[:budget]

    inner_budget = budget - len(prefix) - len(suffix)
    if inner_budget < MIN_BUDGET:
        return shell[:budget]

    inner = _render_dict(dict(obj), inner_budget)
    return prefix + inner + suffix


def _render_counter(obj: collections.Counter, budget: int) -> str:
    prefix = "Counter("
    suffix = ")"

    if not obj:
        return "Counter()"[:budget]

    shell = "Counter()"
    if budget <= len(shell):
        return shell[:budget]

    inner_budget = budget - len(prefix) - len(suffix)
    if inner_budget < MIN_BUDGET:
        return shell[:budget]

    inner = _render_dict(dict(obj.most_common()), inner_budget)
    return prefix + inner + suffix


def _render_deque(obj: collections.deque, budget: int) -> str:
    if not obj:
        return "deque()"[:budget]

    prefix = "deque("
    suffix = ")"
    shell = prefix + suffix

    if budget <= len(shell):
        return shell[:budget]

    inner_budget = budget - len(prefix) - len(suffix)
    if inner_budget < MIN_BUDGET:
        return shell[:budget]

    inner = _render_sequence(obj, inner_budget)
    return prefix + inner + suffix


def _render_object(obj: object, budget: int) -> str:
    """Generic object renderer via attribute decomposition."""
    type_name = type(obj).__name__

    # Try custom __repr__ first — but only if it fits entirely.
    # Skip default "<Foo object at 0x...>" and dataclasses (decomposition
    # is always better since it budgets each field individually).
    if not dataclasses.is_dataclass(obj):
        try:
            r = repr(obj)
            is_default = r.startswith("<") and " object at 0x" in r
            if not is_default and len(r) <= budget:
                return r
        except Exception:
            pass

    # Discover attributes
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        attrs = {
            f.name: getattr(obj, f.name) for f in dataclasses.fields(obj) if f.repr
        }
    elif hasattr(obj, "__dict__"):
        attrs = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    elif hasattr(obj, "__slots__"):
        attrs = {
            s: getattr(obj, s)
            for s in obj.__slots__
            if not s.startswith("_") and hasattr(obj, s)
        }
    else:
        attrs = {}

    return render_attrs(attrs, type_name, budget)
