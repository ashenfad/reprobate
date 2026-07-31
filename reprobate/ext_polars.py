"""Optional renderer for polars objects."""

try:
    import polars as pl
except ImportError:
    pl = None

from ._engine.summaries import (
    TableColumn,
    native_repr_if_fits,
    render_array_summary,
    render_table_summary,
)
from .core import render_child
from .registry import register

if pl is not None:

    @register(pl.DataFrame)
    def render_dataframe(obj: "pl.DataFrame", budget: int) -> str:
        native = native_repr_if_fits(obj, budget)
        if native is not None:
            return native

        columns = tuple(
            TableColumn(name, str(dtype)) for name, dtype in obj.schema.items()
        )
        return render_table_summary(
            "DataFrame", len(obj), columns, budget, render_child
        )

    @register(pl.Series)
    def render_series(obj: "pl.Series", budget: int) -> str:
        native = native_repr_if_fits(obj, budget)
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
            metadata=metadata,
        )
