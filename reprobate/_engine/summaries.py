"""Shared semantic summaries for optional table and array extensions."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .text import single_line

RenderValue = Callable[[object, int], str]


@dataclass(frozen=True)
class TableColumn:
    """Authoritative metadata for one table column."""

    name: object
    dtype: str


def native_repr_if_fits(obj: object, budget: int) -> str | None:
    """Return a normalized native repr only when the normalized form fits."""
    try:
        rendered = repr(obj)
    except Exception:
        return None

    rendered = single_line(rendered)
    return rendered if len(rendered) <= budget else None


def render_table_summary(
    kind: str,
    rows: int,
    columns: Sequence[TableColumn],
    budget: int,
    render_value: RenderValue,
) -> str:
    """Render table shape plus a bounded authoritative column schema."""
    column_count = len(columns)
    shape = f"{rows}x{column_count}"
    base = f"{kind}({shape})"
    if budget <= len(base) or not columns:
        return base[:budget]

    prefix = f"{kind}({shape}, {{"
    suffix = "})"
    if len(prefix) + len(suffix) >= budget:
        return base

    parts: list[str] = []
    used = 0
    for index, column in enumerate(columns):
        dtype = _metadata_text(column.dtype)
        separator = 2 if parts else 0
        omitted = column_count - index - 1
        omission = f"...{omitted} more" if omitted else ""
        omission_cost = (2 if omitted else 0) + len(omission)
        fixed_cost = (
            len(prefix)
            + len(suffix)
            + used
            + separator
            + 2  # ": "
            + len(dtype)
            + omission_cost
        )
        name_budget = budget - fixed_cost
        if name_budget <= 0:
            break

        complete_name = native_repr_if_fits(column.name, name_budget)
        if complete_name is None:
            break
        name = render_value(column.name, name_budget)
        if name != complete_name:
            break
        part = f"{name}: {dtype}"
        if fixed_cost + len(name) > budget:
            break
        parts.append(part)
        used += separator + len(part)

    if not parts:
        return base

    omitted = column_count - len(parts)
    if omitted:
        parts.append(f"...{omitted} more")
    return prefix + ", ".join(parts) + suffix


def render_array_summary(
    kind: str,
    shape: int | Sequence[int],
    dtype: str,
    element_count: int,
    budget: int,
    render_value: RenderValue,
    *,
    value_at: Callable[[int], object] | None = None,
    metadata: Sequence[tuple[str, object]] = (),
    value_limit: int = 20,
) -> str:
    """Render typed array shape, metadata, and bounded representative values."""
    shape_text = _shape_text(shape)
    header = f"{kind}({shape_text}, {_metadata_text(dtype)}"
    base = header + ")"
    if budget <= len(base):
        return base[:budget]

    for label, value in metadata:
        prefix = f", {label}="
        value_budget = budget - len(header) - len(prefix) - 1
        if value_budget <= 0:
            break
        complete_value = native_repr_if_fits(value, value_budget)
        if complete_value is None:
            break
        rendered = render_value(value, value_budget)
        if (
            rendered != complete_value
            or len(header) + len(prefix) + len(rendered) + 1 > budget
        ):
            break
        header += prefix + rendered

    base = header + ")"
    if value_at is None:
        return base

    prefix = header + ", ["
    suffix = "])"
    if len(prefix) + len(suffix) > budget:
        return base
    if element_count == 0:
        return prefix + suffix

    parts: list[str] = []
    used = 0
    for index in range(min(element_count, value_limit)):
        separator = 2 if parts else 0
        omitted = element_count - index - 1
        omission = f"...{omitted} more" if omitted else ""
        omission_cost = (2 if omitted else 0) + len(omission)
        value_budget = (
            budget - len(prefix) - len(suffix) - used - separator - omission_cost
        )
        if value_budget < 3:
            break

        try:
            value = value_at(index)
        except Exception:
            break
        rendered = render_value(value, value_budget)
        if (
            not rendered
            or not _is_informative_sample(rendered)
            or len(rendered) > value_budget
        ):
            break
        parts.append(rendered)
        used += separator + len(rendered)

    if not parts:
        return base

    omitted = element_count - len(parts)
    if omitted:
        parts.append(f"...{omitted} more")
    return prefix + ", ".join(parts) + suffix


def _shape_text(shape: int | Sequence[int]) -> str:
    if isinstance(shape, int):
        return str(shape)
    if not shape:
        return "scalar"
    return "x".join(str(dimension) for dimension in shape)


def _metadata_text(value: object) -> str:
    return single_line(str(value))


def _is_informative_sample(rendered: str) -> bool:
    if not rendered.strip("."):
        return False
    if rendered.startswith("<") and rendered.endswith(">"):
        return ": " in rendered
    return True
