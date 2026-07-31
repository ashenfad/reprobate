"""Budget-bounded rendering engine for Python values and object graphs."""

import collections
import dataclasses
from collections.abc import Iterable
from typing import TypeAlias

from .._session import RenderSession, activate_session
from ..registry import get_renderer
from .context import InferencePolicy, Policy, RenderContext
from .inference import infer_schema
from .schema import RecordSchema, Schema
from .writer import BoundedWriter, BudgetExceeded

_Scalar: TypeAlias = None | bool | int | float

_POLICIES = {"greedy", "even"}
_INFERENCE_POLICIES = {"off", "exact", "best_effort"}
_CIRCULAR = "<...>"
_PROTOCOL_METHOD = "__budget_repr__"


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

    context = RenderContext(policy=policy, inference=inference)
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

    context = RenderContext(policy=policy, inference=inference)
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

    full = _try_full(obj, budget)
    if full is not None:
        return full

    if _is_scalar(obj):
        return _render_scalar(obj, budget)
    if isinstance(obj, str):
        return _render_text(obj, budget, "str")
    if isinstance(obj, bytes):
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
        rendered = renderer(obj, budget)
        rendered = rendered.replace("\r\n", "\\n").replace("\r", "\\r")
        rendered = rendered.replace("\n", "\\n")
        return rendered[:budget]
    finally:
        context.seen.discard(obj_id)


def _is_scalar(obj: object) -> bool:
    return obj is None or isinstance(obj, (bool, int, float))


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
    """Return the longest escaped, quoted prefix with an ellipsis that fits."""
    if budget < 5:
        return ""

    best = ""
    # At least three characters are reserved for the ellipsis. Escape expansion can
    # make a short source prefix consume the entire output budget, so stop once the
    # candidate grows beyond the limit.
    max_items = min(len(obj), budget)
    for size in range(max_items + 1):
        literal = repr(obj[:size])
        candidate = literal[:-1] + "..." + literal[-1]
        if len(candidate) > budget:
            continue
        best = candidate
    return best


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
        open_bracket, close_bracket = (
            ("(", ")") if isinstance(obj, tuple) else ("[", "]")
        )
        values: list[object] = []
        rendered: list[str] = []

        for index, value in enumerate(obj):
            candidate = _minimum(value)
            trial_values = rendered + [candidate]
            omitted = len(obj) - index - 1
            if _sequence_cost(trial_values, omitted, isinstance(obj, tuple)) > budget:
                break
            values.append(value)
            rendered.append(candidate)

        omitted = len(obj) - len(rendered)
        if not rendered:
            inferred = _inferred_summary(obj, context) if allow_inference else None
            if inferred is not None and len(inferred) <= budget:
                return inferred
            count_summary = f"{open_bracket}...{len(obj)} items{close_bracket}"
            if len(count_summary) <= budget:
                return count_summary
            type_summary = f"<{type(obj).__name__}({len(obj)})>"
            if len(type_summary) <= budget:
                return type_summary
            return _fit("...", budget)

        baseline = list(rendered)
        rendered = _refine_values(
            values,
            rendered,
            budget - _sequence_cost(rendered, omitted, isinstance(obj, tuple)),
            context,
        )
        baseline_has_real_value = any(
            _try_full(value, len(value_rendered)) == value_rendered
            for value, value_rendered in zip(values, baseline)
        )
        if allow_inference and rendered == baseline and not baseline_has_real_value:
            inferred = _inferred_summary(obj, context)
            if inferred is not None and len(inferred) <= budget:
                return inferred
        if allow_inference and not any(_CIRCULAR in value for value in rendered):
            inferred = _inferred_summary(obj, context)
            if inferred is not None and "[{'" in inferred and len(inferred) <= budget:
                return inferred
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        body = ", ".join(parts)
        if isinstance(obj, tuple) and len(obj) == 1 and omitted == 0:
            body += ","
        return open_bracket + body + close_bracket
    finally:
        context.seen.discard(obj_id)


def _sequence_cost(rendered: list[str], omitted: int, is_tuple: bool) -> int:
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    body_cost = sum(map(len, parts)) + max(0, len(parts) - 1) * 2
    singleton_comma = 1 if is_tuple and len(rendered) == 1 and omitted == 0 else 0
    return 2 + body_cost + singleton_comma


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
            if _mapping_cost(trial, omitted) > budget:
                break
            keys.append(key_rendered)
            values.append(value)
            rendered.append(f"{key_rendered}: {value_rendered}")

        omitted = len(obj) - len(rendered)
        if not rendered:
            inferred = _inferred_summary(obj, context)
            if inferred is not None and len(inferred) <= budget:
                return inferred
            count_summary = f"{{...{len(obj)} items}}"
            if len(count_summary) <= budget:
                return count_summary
            type_summary = f"<dict({len(obj)})>"
            if len(type_summary) <= budget:
                return type_summary
            return _fit("...", budget)

        value_renderings = [part[len(key) + 2 :] for key, part in zip(keys, rendered)]
        baseline = list(value_renderings)
        available = budget - _mapping_cost(rendered, omitted)
        value_renderings = _refine_values(values, value_renderings, available, context)
        baseline_has_real_value = any(
            _try_full(value, len(value_rendered)) == value_rendered
            for value, value_rendered in zip(values, baseline)
        )
        only_summaries = all(
            value.startswith("<") and value.endswith(">") for value in value_renderings
        )
        if (
            only_summaries
            and not baseline_has_real_value
            and not any(_CIRCULAR in value for value in value_renderings)
        ):
            inferred = _inferred_summary(obj, context)
            if inferred is not None and len(inferred) <= budget:
                return inferred
        rendered = [
            f"{key}: {value_rendered}"
            for key, value_rendered in zip(keys, value_renderings)
        ]
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        return "{" + ", ".join(parts) + "}"
    finally:
        context.seen.discard(obj_id)


def _mapping_cost(rendered: list[str], omitted: int) -> int:
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    return 2 + sum(map(len, parts)) + max(0, len(parts) - 1) * 2


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
        frozen = isinstance(obj, frozenset)
        prefix = "frozenset(" if frozen else ""
        suffix = ")" if frozen else ""
        open_bracket = prefix + "{"
        close_bracket = "}" + suffix
        values: list[object] = []
        rendered: list[str] = []

        for index, value in enumerate(obj):
            candidate = _minimum(value)
            trial_values = rendered + [candidate]
            omitted = len(obj) - index - 1
            if _set_cost(trial_values, omitted, frozen) > budget:
                break
            values.append(value)
            rendered.append(candidate)

        omitted = len(obj) - len(rendered)
        if not rendered:
            inferred = _inferred_summary(obj, context)
            if inferred is not None and len(inferred) <= budget:
                return inferred
            count_summary = f"{open_bracket}...{len(obj)} items{close_bracket}"
            if len(count_summary) <= budget:
                return count_summary
            type_summary = f"<{type(obj).__name__}({len(obj)})>"
            if len(type_summary) <= budget:
                return type_summary
            return _fit("...", budget)

        rendered = _refine_values(
            values,
            rendered,
            budget - _set_cost(rendered, omitted, frozen),
            context,
        )
        parts = rendered + ([f"...{omitted} more"] if omitted else [])
        return open_bracket + ", ".join(parts) + close_bracket
    finally:
        context.seen.discard(obj_id)


def _set_cost(rendered: list[str], omitted: int, frozen: bool) -> int:
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    shell_cost = len("frozenset({})") if frozen else 2
    return shell_cost + sum(map(len, parts)) + max(0, len(parts) - 1) * 2


def _render_deque(obj: collections.deque, budget: int, context: RenderContext) -> str:
    suffix = f", maxlen={obj.maxlen})" if obj.maxlen is not None else ")"
    inner_budget = budget - len("deque(") - len(suffix)
    if inner_budget >= 3:
        inner = _render_sequence(obj, inner_budget, context, allow_inference=False)
        candidate = "deque(" + inner + suffix
        if len(candidate) <= budget:
            return candidate
    return _fit_summary(f"<deque({len(obj)})>", budget)


def _render_counter(
    obj: collections.Counter, budget: int, context: RenderContext
) -> str:
    if len(obj) > 256:
        return _fit_summary(f"<Counter({len(obj)})>", budget)

    ordered = dict(obj.most_common())
    inner_budget = budget - len("Counter(") - 1
    if inner_budget >= 3:
        inner = _render_mapping(ordered, inner_budget, context)
        candidate = f"Counter({inner})"
        if len(candidate) <= budget:
            return candidate
    return _fit_summary(f"<Counter({len(obj)})>", budget)


def _render_defaultdict(
    obj: collections.defaultdict, budget: int, context: RenderContext
) -> str:
    factory_name = _factory_name(obj.default_factory)
    prefix = f"defaultdict({factory_name}, "
    inner_budget = budget - len(prefix) - 1
    if inner_budget >= 3:
        inner = _render_mapping(obj, inner_budget, context)
        candidate = prefix + inner + ")"
        if len(candidate) <= budget:
            return candidate
    return _fit_summary(f"<defaultdict({len(obj)})>", budget)


def _render_namedtuple(obj: tuple, budget: int, context: RenderContext) -> str:
    attrs = dict(zip(type(obj)._fields, obj))
    return _render_tracked_record(obj, attrs, type(obj).__name__, budget, context)


def _render_object(obj: object, budget: int, context: RenderContext) -> str:
    type_name = type(obj).__name__

    if not dataclasses.is_dataclass(obj):
        try:
            native = repr(obj)
        except Exception:
            native = None
        if native is not None:
            is_default = native.startswith("<") and " object at 0x" in native
            if not is_default and len(native) <= budget:
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
        if _record_cost(trial, omitted, shell_cost) > budget:
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
        budget - _record_cost(rendered, omitted, shell_cost),
        context,
    )
    rendered = [
        f"{name}={value_rendered}"
        for name, value_rendered in zip(names, value_renderings)
    ]
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    result = f"{type_name}(" + ", ".join(parts) + ")"
    return result if len(result) <= budget else _fit_summary(tag, budget)


def _record_cost(rendered: list[str], omitted: int, shell_cost: int) -> int:
    parts = rendered + ([f"...{omitted} more"] if omitted else [])
    return shell_cost + sum(map(len, parts)) + max(0, len(parts) - 1) * 2


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

    remaining = len(values)
    for index, value in enumerate(values):
        share = available // remaining if remaining else 0
        candidate = _render_value(value, len(result[index]) + share, context)
        growth = len(candidate) - len(result[index])
        if candidate != result[index] and growth <= share:
            result[index] = candidate
            available -= growth
        remaining -= 1
    return result


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
    if isinstance(obj, collections.defaultdict):
        return f"<defaultdict({len(obj)})>"
    if isinstance(obj, collections.Counter):
        return f"<Counter({len(obj)})>"
    if isinstance(obj, list):
        return f"<list({len(obj)})>"
    if isinstance(obj, tuple):
        return f"<tuple({len(obj)})>"
    if isinstance(obj, dict):
        return f"<dict({len(obj)})>"
    if isinstance(obj, collections.deque):
        return f"<deque({len(obj)})>"
    if isinstance(obj, set):
        return f"<set({len(obj)})>"
    if isinstance(obj, frozenset):
        return f"<frozenset({len(obj)})>"
    return f"<{type(obj).__name__}>"


def _try_full(obj: object, budget: int) -> str | None:
    writer = BoundedWriter(budget)
    try:
        _write_full(obj, writer, set())
    except (BudgetExceeded, _CannotRenderFull):
        return None
    return writer.getvalue()


def _write_full(obj: object, writer: BoundedWriter, seen: set[int]) -> None:
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

    if not isinstance(
        obj,
        (
            list,
            tuple,
            dict,
            set,
            frozenset,
            collections.deque,
            collections.Counter,
            collections.defaultdict,
        ),
    ):
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
            _write_mapping_items(obj.items(), writer, seen)
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
            _write_mapping_items(obj.most_common(), writer, seen)
            writer.write(")")
            return

        if isinstance(obj, dict):
            _write_mapping_items(obj.items(), writer, seen)
            return

        if isinstance(obj, collections.deque):
            if not obj and obj.maxlen is None:
                writer.write("deque()")
                return
            writer.write("deque(")
            _write_sequence_items(obj, "[", "]", writer, seen)
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
            _write_sequence_items(obj, "{", "}", writer, seen)
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
            trailing_comma=isinstance(obj, tuple) and len(obj) == 1,
        )
    finally:
        seen.discard(obj_id)


def _write_mapping_items(
    items: Iterable[tuple[object, object]],
    writer: BoundedWriter,
    seen: set[int],
) -> None:
    writer.write("{")
    for index, (key, value) in enumerate(items):
        if index:
            writer.write(", ")
        _write_full(key, writer, seen)
        writer.write(": ")
        _write_full(value, writer, seen)
    writer.write("}")


def _write_sequence_items(
    values: Iterable[object],
    open_bracket: str,
    close_bracket: str,
    writer: BoundedWriter,
    seen: set[int],
    *,
    trailing_comma: bool = False,
) -> None:
    writer.write(open_bracket)
    for index, value in enumerate(values):
        if index:
            writer.write(", ")
        _write_full(value, writer, seen)
    if trailing_comma:
        writer.write(",")
    writer.write(close_bracket)


def _factory_name(factory: object) -> str:
    if factory is None:
        return "None"
    return getattr(factory, "__name__", type(factory).__name__)


def _inferred_summary(obj: object, context: RenderContext) -> str | None:
    cache_key = (id(obj), False)
    if cache_key not in context.schema_cache:
        context.schema_cache[cache_key] = infer_schema(
            obj,
            context.inference,
            context.inspection,
        )
    schema = context.schema_cache[cache_key]
    if not isinstance(schema, Schema):
        return None
    if isinstance(schema, RecordSchema):
        return f"<{schema.format()}>"
    return f"<{schema.format()}({len(obj)})>"


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
