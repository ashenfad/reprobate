"""Optional renderer for polars objects."""

try:
    import polars as pl
except ImportError:
    pl = None

from ._engine.summaries import (
    TableColumn,
    one_line_native_repr,
    render_array_summary,
    render_table_summary,
)
from .core import render_child
from .registry import register

if pl is not None:

    @register(pl.DataFrame)
    def render_dataframe(obj: "pl.DataFrame", budget: int) -> str:
        native = one_line_native_repr(obj, budget)
        if native is not None:
            return native

        columns = tuple(
            TableColumn(name, str(dtype)) for name, dtype in obj.schema.items()
        )
        return render_table_summary(
            "DataFrame", len(obj), columns, budget, render_child, row_at=obj.row
        )

    @register(pl.Series)
    def render_series(obj: "pl.Series", budget: int) -> str:
        native = one_line_native_repr(obj, budget)
        if native is not None:
            return native

        metadata = (("name", obj.name),) if obj.name is not None else ()
        return render_array_summary(
            "Series",
            len(obj),
            str(obj.dtype),
            len(obj),
            budget,
            render_child,
            value_at=obj.__getitem__,
            metadata=metadata,
        )
