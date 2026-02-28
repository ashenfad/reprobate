"""Optional renderer for polars objects."""

try:
    import polars as pl
except ImportError:
    pl = None

from .core import render_child
from .registry import register

if pl is not None:

    @register(pl.DataFrame)
    def render_dataframe(obj: "pl.DataFrame", budget: int) -> str:
        try:
            r = repr(obj)
            if len(r) <= budget:
                return r
        except Exception:
            pass

        rows, cols = obj.shape
        col_names = obj.columns
        header = f"DataFrame({rows}x{cols}"

        if budget <= len(header) + 1:
            return f"DataFrame({rows}x{cols})"[:budget]

        remaining = budget - len(header) - 5  # ", [" before cols, "])" at end
        if remaining < 5:
            return (header + ")")[:budget]

        # Show column names
        col_parts: list[str] = []
        used = 0

        for i, name in enumerate(col_names):
            sep = 2 if col_parts else 0
            omitted = len(col_names) - i - 1
            reserve = len(f", ...{omitted} more") if omitted > 0 else 0
            avail = remaining - used - sep - reserve

            r = render_child(name, avail)
            if len(r) > avail or avail < 3:
                break
            col_parts.append(r)
            used += len(r) + sep

        omitted = len(col_names) - len(col_parts)
        if omitted > 0:
            col_parts.append(f"...{omitted} more")

        return header + ", [" + ", ".join(col_parts) + "])"

    @register(pl.Series)
    def render_series(obj: "pl.Series", budget: int) -> str:
        try:
            r = repr(obj)
            if len(r) <= budget:
                return r
        except Exception:
            pass

        dtype = str(obj.dtype)
        n = len(obj)
        name_part = f", name={obj.name!r}" if obj.name is not None else ""
        header = f"Series({n}, {dtype}{name_part})"

        return header[:budget]
