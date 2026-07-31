"""Budget-bounded rendering engine for Python values and object graphs."""

import collections
import dataclasses
from collections.abc import Iterable
from typing import TypeAlias

from .._session import RenderSession, activate_session
from ..registry import get_renderer
from .context import (
    InferencePolicy,
    InspectionBudget,
    Policy,
    RenderContext,
    render_work_budget,
)
from .inference import infer_schema
from .planning import allocate_even
from .schema import RecordSchema, Schema, SequenceSchema
from .text import single_line
from .writer import BoundedWriter, BudgetExceeded

_Scalar: TypeAlias = None | bool | int | float

_POLICIES = {"greedy", "even"}
_INFERENCE_POLICIES = {"off", "exact", "best_effort"}
_CIRCULAR = "<...>"
_PROTOCOL_METHOD = "__budget_repr__"

_STRUCTURED_TYPES = (
    list,
    tuple,
    dict,
    set,
    frozenset,
    collections.deque,
)
_EXACT_STRUCTURED = {
    list,
    tuple,
    dict,
    set,
    frozenset,
    collections.deque,
    collections.Counter,
    collections.defaultdict,
}
_KNOWN_STRUCTURED_REPR_OWNERS = _EXACT_STRUCTURED | {collections.OrderedDict}


class _CannotRenderFull(Exception):
    """Raised when the bounded complete-render path does not support a value."""


def render(
    obj: object,
    budget: int = 200,
    policy: Policy = "greedy",
    *,
    inference: InferencePolicy = "best_effort",
) -> str:
    """Render through the engine used by the public facade."""
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if policy not in _POLICIES:
        raise ValueError(f"unknown rendering policy: {policy!r}")
    if inference not in _INFERENCE_POLICIES:
        raise ValueError(f"unknown inference policy: {inference!r}")
    if budget == 0:
        return ""

    context = RenderContext(
        policy=policy,
        inference=inference,
        work=render_work_budget(budget),
    )
    session = RenderSession(
        render_child=lambda child, child_budget: _render_value(
            child, child_budget, context
        ),
        render_attrs=lambda attrs, type_name, attrs_budget: _render_record(
            attrs, type_name, attrs_budget, context
        ),
    )
    with activate_session(session):
        result = _render_value(obj, budget, context)
    if len(result) > budget:
        raise AssertionError(f"rendering engine exceeded budget {budget}: {result!r}")
    return result


def render_attrs(
    attrs: dict[str, object],
    type_name: str,
    budget: int,
    *,
    policy: Policy = "greedy",
    inference: InferencePolicy = "best_effort",
) -> str:
    """Render a standalone record through the rendering engine."""
    if budget < 0:
        raise ValueError("budget must be nonnegative")
    if policy not in _POLICIES:
        raise ValueError(f"unknown rendering policy: {policy!r}")
    if inference not in _INFERENCE_POLICIES:
        raise ValueError(f"unknown inference policy: {inference!r}")
    if budget == 0:
        return ""

    context = RenderContext(
        policy=policy,
        inference=inference,
        work=render_work_budget(budget),
    )
    session = RenderSession(
        render_child=lambda child, child_budget: _render_value(
            child, child_budget, context
        ),
        render_attrs=lambda child_attrs, child_type, child_budget: _render_record(
            child_attrs, child_type, child_budget, context
        ),
    )
    with activate_session(session):
        return _render_record(attrs, type_name, budget, context)


def _render_value(obj: object, budget: int, context: RenderContext) -> str:
    if budget <= 0:
        return ""

    custom = _custom_renderer(obj)
    if custom is not None:
        return _render_custom(obj, budget, context, custom)

    if isinstance(obj, tuple) and hasattr(type(obj), "_fields"):
        return _render_namedtuple(obj, budget, context)

    if isinstance(obj, _STRUCTURED_TYPES) and not _faithful_structured(obj):
        native = _native_structured_repr(obj, budget)
        if native is not None:
            return native

    full = _try_full(obj, budget, context.work)
    if full is not None:
        return full

    if _is_scalar(obj) or isinstance(obj, (str, bytes)):
        if not _faithful_scalar(obj):
            native = _normalized_native_repr(obj, budget)
            if native is not None:
                return native
        if _is_scalar(obj):
            return _render_scalar(obj, budget)
        if isinstance(obj, str):
            return _render_text(obj, budget, "str")
        return _render_text(obj, budget, "bytes")
    if isinstance(obj, collections.defaultdict):
        return _render_defaultdict(obj, budget, context)
    if isinstance(obj, collections.Counter):
        return _render_counter(obj, budget, context)
    if isinstance(obj, dict):
        return _render_mapping(obj, budget, context)
    if isinstance(obj, collections.deque):
        return _render_deque(obj, budget, context)
    if isinstance(obj, (list, tuple)):
        return _render_sequence(obj, budget, context)
    if isinstance(obj, (set, frozenset)):
        return _render_set(obj, budget, context)
    return _render_object(obj, budget, context)


def _custom_renderer(obj: object):
    method = getattr(type(obj), _PROTOCOL_METHOD, None)
    if method is not None:
        return lambda value, budget: method(value, budget)
    return get_renderer(type(obj))


def _render_custom(obj: object, budget: int, context: RenderContext, renderer) -> str:
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)
    context.seen.add(obj_id)
    try:
        rendered = single_line(renderer(obj, budget))
        truncated = rendered[:budget]
        if truncated != rendered:
            # Do not end on a dangling backslash that would turn a two-character
            # escape into a misleading fragment.
            dangling = len(truncated) - len(truncated.rstrip("\\"))
            if dangling % 2:
                truncated = truncated[:-1]
        return truncated
    finally:
        context.seen.discard(obj_id)


def _is_scalar(obj: object) -> bool:
    return obj is None or isinstance(obj, (bool, int, float))


def _faithful_scalar(obj: object) -> bool:
    """True when the builtin scalar/text rendering matches the object's own repr."""
    if obj is None or isinstance(obj, bool):
        return True
    for base in (int, float, str, bytes):
        if isinstance(obj, base):
            return type(obj) is base or type(obj).__repr__ is base.__repr__
    return True


def _faithful_structured(obj: object) -> bool:
    """True when structural container output matches the object's own repr.

    Exact builtin containers always qualify. dict/list/tuple subclasses qualify
    while they inherit the base repr, because that repr carries no class name.
    set, frozenset, deque, Counter, and defaultdict reprs embed the class name,
    so their subclasses must degrade through their own repr instead.
    """
    cls = type(obj)
    if cls in _EXACT_STRUCTURED:
        return True
    for base in (dict, list, tuple):
        if isinstance(obj, base):
            return cls.__repr__ is base.__repr__
    return False


def _native_structured_repr(obj: object, budget: int) -> str | None:
    """Honor a container subclass repr when it is affordable, else degrade."""
    try:
        # Known container reprs spell every entry, so large values cannot fit and
        # their potentially expensive reprs need not be built. A user override
        # may instead return a compact summary independent of container length.
        if not _has_custom_structured_repr(obj) and len(obj) * 3 > budget:
            return None
    except Exception:
        return None
    return _normalized_native_repr(obj, budget)


def _has_custom_structured_repr(obj: object) -> bool:
    """Whether the effective repr comes from a user-defined container class."""
    owner = next(
        (cls for cls in type(obj).__mro__ if "__repr__" in cls.__dict__),
        object,
    )
    return owner not in _KNOWN_STRUCTURED_REPR_OWNERS


def _normalized_native_repr(obj: object, budget: int) -> str | None:
    """Return a single-line native repr when it fits and is not the default."""
    try:
        native = repr(obj)
    except Exception:
        return None
    if native.startswith("<") and " object at 0x" in native:
        return None
    native = single_line(native)
    return native if len(native) <= budget else None


def _render_scalar(obj: _Scalar, budget: int) -> str:
    full = _bounded_scalar_repr(obj, budget)
    stub = f"<{type(obj).__name__}>" if obj is not None else "<None>"
    if full is not None:
        return full
    if len(stub) <= budget:
        return stub
    return _fit("...", budget)


def _render_text(obj: str | bytes, budget: int, kind: str) -> str:
    preview = _literal_preview(obj, budget)
    length_prefix = f"<{kind}({len(obj)}): "
    inner_budget = budget - len(length_prefix) - 1

    if inner_budget >= 12:
        inner = _literal_preview(obj, inner_budget)
        if len(inner) >= 8:
            candidate = f"{length_prefix}{inner}>"
            if len(candidate) <= budget:
                return candidate

    if preview:
        return preview

    sized_stub = f"<{kind}({len(obj)})>"
    if len(sized_stub) <= budget:
        return sized_stub
    return _fit(f"<{kind}>", budget)


def _literal_preview(obj: str | bytes, budget: int) -> str:
    """Return the longest escaped, quoted prefix with an ellipsis that fits.

    ``len(repr(obj[:size]))`` is nondecreasing in ``size``: every character adds
    at least one output character, and a quote-style flip only ever lengthens
    the escaped form (the single-to-double flip happens on the first quote of a
    quoteless prefix, the double-to-single flip re-escapes prior quotes). That
    monotonicity makes the longest fitting prefix binary-searchable.
    """
    if budget < 5:
        return ""

    def candidate(size: int) -> str:
        literal = repr(obj[:size])
        return literal[:-1] + "..." + literal[-1]

    # Each source character costs at least one output character, so prefixes
    # longer than the budget can never fit.
    low, high = 0, min(len(obj), budget)
    if len(candidate(low)) > budget:
        return ""
    while low < high:
        middle = (low + high + 1) // 2
        if len(candidate(middle)) <= budget:
            low = middle
        else:
            high = middle - 1
    return candidate(low)


def _render_sequence(
    obj: list[object] | tuple[object, ...] | collections.deque,
    budget: int,
    context: RenderContext,
    *,
    allow_inference: bool = True,
) -> str:
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)

    context.seen.add(obj_id)
    try:
        is_tuple = isinstance(obj, tuple)
        open_bracket, close_bracket = ("(", ")") if is_tuple else ("[", "]")

        product = _uniform_product(obj, budget, context, is_tuple)
        if product is not None:
            return product

        values: list[object] = []
        rendered: list[str] = []

        for index, value in enumerate(obj):
            candidate = _minimum(value)
            trial_values = rendered + [candidate]
            omitted = len(obj) - index - 1
            cost = _parts_cost(trial_values, omitted, 2, singleton_comma=is_tuple)
            if cost > budget:
                break
            values.append(value)
            rendered.append(candidate)

        omitted = len(obj) - len(rendered)
        if not rendered:
            return _collapsed_summary(
                obj, budget, context, open_bracket, close_bracket, allow_inference
            )

        if allow_inference:
            schema = _inferred_schema(obj, context)
            if (
                isinstance(schema, SequenceSchema)
                and isinstance(schema.item, RecordSchema)
                and schema.item.complete
            ):
                # A record sequence communicates more through its shared shape
                # plus complete sample records than through the first records
                # alone. Fall through when the summary cannot fit.
                summary = _inferred_summary(obj, budget, context)
                if summary is not None:
                    return summary

        baseline = list(rendered)
        rendered = _refine_values(
            values,
            rendered,
            budget - _parts_cost(rendered, omitted, 2, singleton_comma=is_tuple),
            context,
        )
        if allow_inference:
            summary, sample_count = _sampled_summary(obj, budget, context)
            if summary is not None:
                # Prefer the form that shows more complete values; ties keep
                # the plain form with its previews and positional detail. A
                # bare summary may still replace a skeleton that refinement
                # could not improve at all.
                plain_complete = _complete_count(values, rendered, context)
                if sample_count > plain_complete or (
                    plain_complete == 0 and rendered == baseline
                ):
                    return summary
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        body = ", ".join(parts)
        if is_tuple and len(obj) == 1 and omitted == 0:
            body += ","
        return open_bracket + body + close_bracket
    finally:
        context.seen.discard(obj_id)


def _parts_cost(
    rendered: list[str],
    omitted: int,
    shell: int,
    *,
    singleton_comma: bool = False,
) -> int:
    """Cost of shell plus comma-joined parts and a truthful omission marker."""
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    cost = shell + sum(map(len, parts)) + max(0, len(parts) - 1) * 2
    if singleton_comma and len(rendered) == 1 and not omitted:
        cost += 1
    return cost


def _has_complete_baseline(
    values: list[object],
    baseline: list[str],
    context: RenderContext,
) -> bool:
    """True when any baseline entry already shows a complete value."""
    return any(
        _try_full(value, len(rendered), context.work) == rendered
        for value, rendered in zip(values, baseline)
    )


def _complete_count(
    values: list[object],
    rendered: list[str],
    context: RenderContext,
) -> int:
    """Number of entries whose rendering already shows a complete value."""
    return sum(
        1
        for value, value_rendered in zip(values, rendered)
        if _try_full(value, len(value_rendered), context.work) == value_rendered
    )


_UNIFORM_MISSING = object()


def _uniform_product(
    obj: list | tuple | collections.deque,
    budget: int,
    context: RenderContext,
    is_tuple: bool,
) -> str | None:
    """Render ``[x] * n`` when every element is provably the same value.

    The product expression is lossless, so it outranks partial values and
    schema summaries; it applies only to whole containers and never to runs.
    Proving uniformity requires reading every element, so the scan must fit
    inside the remaining work allowance — larger budgets unlock larger proofs.
    """
    if len(obj) < 2 or len(obj) > context.work.remaining:
        return None
    element = _uniform_element(obj, context.work)
    if element is _UNIFORM_MISSING:
        return None
    rendered = _try_full(element, budget, context.work)
    if rendered is None:
        return None
    if is_tuple:
        candidate = f"({rendered},) * {len(obj)}"
    else:
        candidate = f"[{rendered}] * {len(obj)}"
    return candidate if len(candidate) <= budget else None


def _uniform_element(
    obj: list | tuple | collections.deque,
    work: InspectionBudget,
) -> object:
    """Return the shared element, or ``_UNIFORM_MISSING`` when not uniform.

    Identity covers the common ``[x] * n`` construction. Distinct objects
    must be scalars of the same type with equal values, and floats must also
    agree on repr so ``0.0`` never stands in for ``-0.0``.
    """
    iterator = iter(obj)
    first = next(iterator)
    for value in iterator:
        if not work.consume():
            return _UNIFORM_MISSING
        if value is first:
            continue
        if type(value) is not type(first):
            return _UNIFORM_MISSING
        if not isinstance(first, (bool, int, float, str, bytes)):
            return _UNIFORM_MISSING
        if value != first:
            return _UNIFORM_MISSING
        if isinstance(first, float) and repr(value) != repr(first):
            return _UNIFORM_MISSING
    return first


def _collapsed_summary(
    obj,
    budget: int,
    context: RenderContext,
    open_bracket: str,
    close_bracket: str,
    allow_inference: bool = True,
) -> str:
    """Degradation ladder for a container whose skeleton cannot fit."""
    if allow_inference:
        summary = _inferred_summary(obj, budget, context)
        if summary is not None:
            return summary
    count_summary = f"{open_bracket}...{len(obj)} items{close_bracket}"
    if len(count_summary) <= budget:
        return count_summary
    type_summary = f"<{type(obj).__name__}({len(obj)})>"
    if len(type_summary) <= budget:
        return type_summary
    return _fit("...", budget)


def _render_mapping(obj: dict, budget: int, context: RenderContext) -> str:
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)

    context.seen.add(obj_id)
    try:
        keys: list[str] = []
        values: list[object] = []
        rendered: list[str] = []

        for index, (key, value) in enumerate(obj.items()):
            key_rendered = _minimum_key(key)
            value_rendered = _minimum(value)
            trial = rendered + [f"{key_rendered}: {value_rendered}"]
            omitted = len(obj) - index - 1
            if _parts_cost(trial, omitted, 2) > budget:
                break
            keys.append(key_rendered)
            values.append(value)
            rendered.append(f"{key_rendered}: {value_rendered}")

        omitted = len(obj) - len(rendered)
        if not rendered:
            return _collapsed_summary(obj, budget, context, "{", "}")

        value_renderings = [part[len(key) + 2 :] for key, part in zip(keys, rendered)]
        baseline = list(value_renderings)
        available = budget - _parts_cost(rendered, omitted, 2)
        value_renderings = _refine_values(values, value_renderings, available, context)
        only_summaries = all(
            value.startswith("<") and value.endswith(">") for value in value_renderings
        )
        if (
            only_summaries
            and not any(_CIRCULAR in value for value in value_renderings)
            and not _has_complete_baseline(values, baseline, context)
        ):
            inferred = _inferred_summary(obj, budget, context)
            if inferred is not None:
                return inferred
        rendered = [
            f"{key}: {value_rendered}"
            for key, value_rendered in zip(keys, value_renderings)
        ]
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        return "{" + ", ".join(parts) + "}"
    finally:
        context.seen.discard(obj_id)


def _render_set(
    obj: set[object] | frozenset[object],
    budget: int,
    context: RenderContext,
) -> str:
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)

    context.seen.add(obj_id)
    try:
        # frozensets and set/frozenset subclasses spell their type name; the
        # brace-only form is reserved for exactly ``set``.
        named = type(obj) is not set
        prefix = f"{type(obj).__name__}(" if named else ""
        suffix = ")" if named else ""
        open_bracket = prefix + "{"
        close_bracket = "}" + suffix
        shell = len(open_bracket) + len(close_bracket)
        values: list[object] = []
        rendered: list[str] = []

        for index, value in enumerate(obj):
            candidate = _minimum(value)
            trial_values = rendered + [candidate]
            omitted = len(obj) - index - 1
            if _parts_cost(trial_values, omitted, shell) > budget:
                break
            values.append(value)
            rendered.append(candidate)

        omitted = len(obj) - len(rendered)
        if not rendered:
            return _collapsed_summary(obj, budget, context, open_bracket, close_bracket)

        rendered = _refine_values(
            values,
            rendered,
            budget - _parts_cost(rendered, omitted, shell),
            context,
        )
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        return open_bracket + ", ".join(parts) + close_bracket
    finally:
        context.seen.discard(obj_id)


def _render_deque(obj: collections.deque, budget: int, context: RenderContext) -> str:
    name = type(obj).__name__
    suffix = f", maxlen={obj.maxlen})" if obj.maxlen is not None else ")"
    inner_budget = budget - len(name) - 1 - len(suffix)
    if inner_budget >= 3:
        inner = _render_sequence(obj, inner_budget, context, allow_inference=False)
        candidate = f"{name}(" + inner + suffix
        if len(candidate) <= budget:
            return candidate
    summary = _inferred_summary(obj, budget, context)
    if summary is not None:
        return summary
    return _fit_summary(f"<{name}({len(obj)})>", budget)


def _render_counter(
    obj: collections.Counter, budget: int, context: RenderContext
) -> str:
    name = type(obj).__name__
    if len(obj) > 256:
        return _fit_summary(f"<{name}({len(obj)})>", budget)

    # The counter renders through an ordered copy, so cycle detection must
    # track the original object; the copies get fresh ids on every level.
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)
    context.seen.add(obj_id)
    try:
        ordered = _counter_ordered(obj)
        inner_budget = budget - len(name) - 2
        if inner_budget >= 3:
            inner = _render_mapping(ordered, inner_budget, context)
            candidate = f"{name}({inner})"
            if len(candidate) <= budget:
                return candidate
        return _fit_summary(f"<{name}({len(obj)})>", budget)
    finally:
        context.seen.discard(obj_id)


def _counter_ordered(obj: collections.Counter) -> dict:
    """Most-common order, falling back to insertion order like Counter.__repr__."""
    try:
        return dict(obj.most_common())
    except TypeError:
        return dict(obj)


def _render_defaultdict(
    obj: collections.defaultdict, budget: int, context: RenderContext
) -> str:
    name = type(obj).__name__
    factory_name = _factory_name(obj.default_factory)
    prefix = f"{name}({factory_name}, "
    inner_budget = budget - len(prefix) - 1
    if inner_budget >= 3:
        inner = _render_mapping(obj, inner_budget, context)
        candidate = prefix + inner + ")"
        if len(candidate) <= budget:
            return candidate
    return _fit_summary(f"<{name}({len(obj)})>", budget)


def _render_namedtuple(obj: tuple, budget: int, context: RenderContext) -> str:
    attrs = dict(zip(type(obj)._fields, obj))
    return _render_tracked_record(obj, attrs, type(obj).__name__, budget, context)


def _render_object(obj: object, budget: int, context: RenderContext) -> str:
    type_name = type(obj).__name__

    if not dataclasses.is_dataclass(obj):
        native = _normalized_native_repr(obj, budget)
        if native is not None:
            return native

    attrs = _object_attrs(obj)
    return _render_tracked_record(obj, attrs, type_name, budget, context)


def _object_attrs(obj: object) -> dict[str, object]:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {
            field.name: getattr(obj, field.name)
            for field in dataclasses.fields(obj)
            if field.repr
        }
    if hasattr(obj, "__dict__"):
        return {
            key: value for key, value in vars(obj).items() if not key.startswith("_")
        }

    attrs: dict[str, object] = {}
    for cls in reversed(type(obj).__mro__):
        slots = vars(cls).get("__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot in slots:
            if (
                slot not in {"__dict__", "__weakref__"}
                and not slot.startswith("_")
                and hasattr(obj, slot)
            ):
                attrs[slot] = getattr(obj, slot)
    return attrs


def _render_tracked_record(
    obj: object,
    attrs: dict[str, object],
    type_name: str,
    budget: int,
    context: RenderContext,
) -> str:
    obj_id = id(obj)
    if obj_id in context.seen:
        return _fit(_CIRCULAR, budget)
    context.seen.add(obj_id)
    try:
        return _render_record(attrs, type_name, budget, context)
    finally:
        context.seen.discard(obj_id)


def _render_record(
    attrs: dict[str, object],
    type_name: str,
    budget: int,
    context: RenderContext,
) -> str:
    tag = f"<{type_name}>"
    if not attrs:
        return _fit_summary(tag, budget)

    values: list[object] = []
    names: list[str] = []
    rendered: list[str] = []
    items = list(attrs.items())
    shell_cost = len(type_name) + 2

    for index, (name, value) in enumerate(items):
        value_rendered = _minimum(value)
        trial = rendered + [f"{name}={value_rendered}"]
        omitted = len(items) - index - 1
        if _parts_cost(trial, omitted, shell_cost) > budget:
            break
        names.append(name)
        values.append(value)
        rendered.append(f"{name}={value_rendered}")

    omitted = len(items) - len(rendered)
    if not rendered:
        return _fit_summary(tag, budget)

    value_renderings = [part[len(name) + 1 :] for name, part in zip(names, rendered)]
    value_renderings = _refine_values(
        values,
        value_renderings,
        budget - _parts_cost(rendered, omitted, shell_cost),
        context,
    )
    rendered = [
        f"{name}={value_rendered}"
        for name, value_rendered in zip(names, value_renderings)
    ]
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    result = f"{type_name}(" + ", ".join(parts) + ")"
    return result if len(result) <= budget else _fit_summary(tag, budget)


def _refine_values(
    values: list[object],
    rendered: list[str],
    available: int,
    context: RenderContext,
) -> list[str]:
    if available <= 0 or not rendered:
        return rendered

    result = list(rendered)
    if context.policy == "greedy":
        for index, value in enumerate(values):
            candidate = _render_value(value, len(result[index]) + available, context)
            growth = len(candidate) - len(result[index])
            if candidate != result[index] and growth <= available:
                result[index] = candidate
                available -= growth
            if available <= 0:
                break
        return result

    return _refine_values_even(values, result, available, context)


def _refine_values_even(
    values: list[object],
    rendered: list[str],
    available: int,
    context: RenderContext,
) -> list[str]:
    """Plan sibling demand before max-min allocation and one render pass."""
    result = list(rendered)
    complete: list[str | None] = [None] * len(values)

    # First accept complete representations that already fit the baseline. A shorter
    # complete value is both more truthful and returns its saved characters before
    # sibling demand is measured.
    for index, value in enumerate(values):
        full = _try_complete_for_plan(value, len(result[index]), context)
        if full is None:
            continue
        available += len(result[index]) - len(full)
        result[index] = full
        complete[index] = full

    demands: list[int | None] = []
    for index, value in enumerate(values):
        if complete[index] is not None:
            demands.append(0)
            continue

        full = _try_complete_for_plan(
            value,
            len(result[index]) + available,
            context,
        )
        if full is None:
            demands.append(None)
            continue
        complete[index] = full
        demands.append(len(full) - len(result[index]))

    allocations = allocate_even(demands, available)
    carry = 0

    for index, value in enumerate(values):
        allowance = allocations[index] + carry
        demand = demands[index]
        full = complete[index]
        if full is not None and demand is not None and allowance >= demand:
            candidate = full
        elif allowance > 0:
            candidate = _render_value(value, len(result[index]) + allowance, context)
        else:
            candidate = result[index]

        growth = len(candidate) - len(result[index])
        if candidate != result[index] and growth <= allowance:
            result[index] = candidate
            carry = allowance - growth
        else:
            carry = allowance

    return result


def _try_complete_for_plan(
    obj: object, budget: int, context: RenderContext
) -> str | None:
    """Probe complete built-in output without invoking opaque customization hooks."""
    if _custom_renderer(obj) is not None:
        return None
    if isinstance(obj, tuple) and hasattr(type(obj), "_fields"):
        return None
    return _try_full(obj, budget, context.work)


def _minimum_key(obj: object) -> str:
    full = _try_full(obj, 40)
    if full is not None:
        return full
    if isinstance(obj, (str, bytes)):
        preview = _literal_preview(obj, 40)
        if preview:
            return preview
    return _minimum(obj)


def _minimum(obj: object) -> str:
    if _is_scalar(obj):
        stub = f"<{type(obj).__name__}>" if obj is not None else "<None>"
        full = _bounded_scalar_repr(obj, len(stub))
        return full if full is not None else stub
    if isinstance(obj, str):
        stub = f"<str({len(obj)})>"
        if len(obj) + 2 <= len(stub):
            full = repr(obj)
            if len(full) <= len(stub):
                return full
        return stub
    if isinstance(obj, bytes):
        stub = f"<bytes({len(obj)})>"
        if len(obj) + 3 <= len(stub):
            full = repr(obj)
            if len(full) <= len(stub):
                return full
        return stub
    if isinstance(obj, _STRUCTURED_TYPES):
        return f"<{type(obj).__name__}({len(obj)})>"
    return f"<{type(obj).__name__}>"


def _try_full(
    obj: object,
    budget: int,
    work: InspectionBudget | None = None,
) -> str | None:
    writer = BoundedWriter(budget)
    try:
        _write_full(obj, writer, set(), work)
    except (BudgetExceeded, _CannotRenderFull):
        return None
    return writer.getvalue()


def _write_full(
    obj: object,
    writer: BoundedWriter,
    seen: set[int],
    work: InspectionBudget | None = None,
) -> None:
    if work is not None and not work.consume():
        raise _CannotRenderFull
    if isinstance(obj, (str, bytes)) or _is_scalar(obj):
        # A subclass with its own repr controls its own spelling; the probe
        # must not claim the builtin rendering is complete for it.
        if not _faithful_scalar(obj):
            raise _CannotRenderFull

    if isinstance(obj, str):
        # A string repr needs at least one character per source character plus two
        # quotes. Reject obvious overflows before allocating the complete repr.
        if len(obj) + 2 > writer.remaining:
            raise BudgetExceeded
        writer.write(repr(obj))
        return

    if isinstance(obj, bytes):
        # A bytes repr has the same lower bound plus its leading ``b`` marker.
        if len(obj) + 3 > writer.remaining:
            raise BudgetExceeded
        writer.write(repr(obj))
        return

    if _is_scalar(obj):
        rendered = _bounded_scalar_repr(obj, writer.remaining)
        if rendered is None:
            raise BudgetExceeded
        writer.write(rendered)
        return

    # Reject namedtuples and container subclasses whose repr differs from the
    # structural spelling; they degrade through their own representations.
    if not _faithful_structured(obj):
        raise _CannotRenderFull

    obj_id = id(obj)
    if obj_id in seen:
        raise _CannotRenderFull
    seen.add(obj_id)
    try:
        if isinstance(obj, collections.defaultdict):
            writer.write("defaultdict(")
            writer.write(repr(obj.default_factory))
            writer.write(", ")
            _write_mapping_items(obj.items(), writer, seen, work)
            writer.write(")")
            return

        if isinstance(obj, collections.Counter):
            if not obj:
                writer.write("Counter()")
                return
            # Avoid sorting a large counter merely to discover that it cannot fit.
            if len(obj) * 3 > writer.remaining:
                raise BudgetExceeded
            writer.write("Counter(")
            _write_mapping_items(_counter_ordered(obj).items(), writer, seen, work)
            writer.write(")")
            return

        if isinstance(obj, dict):
            _write_mapping_items(obj.items(), writer, seen, work)
            return

        if isinstance(obj, collections.deque):
            if not obj and obj.maxlen is None:
                writer.write("deque()")
                return
            writer.write("deque(")
            _write_sequence_items(obj, "[", "]", writer, seen, work)
            if obj.maxlen is not None:
                writer.write(f", maxlen={obj.maxlen}")
            writer.write(")")
            return

        if isinstance(obj, (set, frozenset)):
            if not obj:
                writer.write("frozenset()" if isinstance(obj, frozenset) else "set()")
                return
            if isinstance(obj, frozenset):
                writer.write("frozenset(")
            _write_sequence_items(obj, "{", "}", writer, seen, work)
            if isinstance(obj, frozenset):
                writer.write(")")
            return

        open_bracket, close_bracket = (
            ("(", ")") if isinstance(obj, tuple) else ("[", "]")
        )
        _write_sequence_items(
            obj,
            open_bracket,
            close_bracket,
            writer,
            seen,
            work,
            trailing_comma=isinstance(obj, tuple) and len(obj) == 1,
        )
    finally:
        seen.discard(obj_id)


def _write_mapping_items(
    items: Iterable[tuple[object, object]],
    writer: BoundedWriter,
    seen: set[int],
    work: InspectionBudget | None = None,
) -> None:
    writer.write("{")
    for index, (key, value) in enumerate(items):
        if index:
            writer.write(", ")
        _write_full(key, writer, seen, work)
        writer.write(": ")
        _write_full(value, writer, seen, work)
    writer.write("}")


def _write_sequence_items(
    values: Iterable[object],
    open_bracket: str,
    close_bracket: str,
    writer: BoundedWriter,
    seen: set[int],
    work: InspectionBudget | None = None,
    *,
    trailing_comma: bool = False,
) -> None:
    writer.write(open_bracket)
    for index, value in enumerate(values):
        if index:
            writer.write(", ")
        _write_full(value, writer, seen, work)
    if trailing_comma:
        writer.write(",")
    writer.write(close_bracket)


def _factory_name(factory: object) -> str:
    if factory is None:
        return "None"
    return getattr(factory, "__name__", type(factory).__name__)


def _inferred_schema(obj: object, context: RenderContext) -> Schema | None:
    key = id(obj)
    entry = context.schema_cache.get(key)
    if entry is None:
        schema = infer_schema(obj, context.inference, context.inspection)
        entry = (obj, schema)
        context.schema_cache[key] = entry
    schema = entry[1]
    return schema if isinstance(schema, Schema) else None


def _inferred_summary(obj: object, budget: int, context: RenderContext) -> str | None:
    summary, _ = _sampled_summary(obj, budget, context)
    return summary


def _sampled_summary(
    obj: object, budget: int, context: RenderContext
) -> tuple[str | None, int]:
    """Render the best schema summary that fits, plus its complete-sample count.

    Sequences prefer the sampled form ``<list[str](200): 'alice', 'bob', ...>``
    from the design's degradation ladder, then the bare ``<list[str](200)>``.
    Mappings and records use their schema-only forms and carry zero samples.
    """
    schema = _inferred_schema(obj, context)
    if schema is None:
        return None, 0
    if isinstance(schema, RecordSchema):
        summary = f"<{schema.format()}>"
        return (summary if len(summary) <= budget else None), 0

    bare = f"<{schema.format()}({len(obj)})>"
    if len(bare) > budget:
        return None, 0
    if isinstance(obj, dict) or not len(obj):
        return bare, 0

    head = f"<{schema.format()}({len(obj)}): "
    samples: list[str] = []
    used = 0
    for value in obj:
        # Cost so far plus separators for the next sample and the ", ...>" tail.
        allowance = budget - len(head) - used - 2 * len(samples) - 6
        if allowance <= 0:
            break
        sample = _try_complete_for_plan(value, allowance, context)
        if sample is None:
            break
        samples.append(sample)
        used += len(sample)
    if not samples:
        return bare, 0
    return head + ", ".join(samples) + ", ...>", len(samples)


def _bounded_scalar_repr(obj: _Scalar, budget: int) -> str | None:
    """Return a scalar repr only when it can fit without a huge conversion."""
    if isinstance(obj, int) and not isinstance(obj, bool):
        bits = abs(obj).bit_length()
        decimal_lower_bound = (
            1 if bits == 0 else int((bits - 1) * 0.3010299956639812) + 1
        )
        if obj < 0:
            decimal_lower_bound += 1
        if decimal_lower_bound > budget:
            return None

    try:
        rendered = repr(obj)
    except (OverflowError, ValueError):
        return None
    return rendered if len(rendered) <= budget else None


def _fit_summary(value: str, budget: int) -> str:
    if len(value) <= budget:
        return value
    return _fit("...", budget)


def _fit(value: str, budget: int) -> str:
    return value[:budget]
