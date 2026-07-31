"""Optional renderer for PyArrow objects."""

try:
    import pyarrow as pa
except ImportError:
    pa = None

from ._engine.summaries import (
    TableColumn,
    native_repr_if_fits,
    render_array_summary,
    render_table_summary,
)
from .core import render_child
from .registry import register

if pa is not None:

    @register(pa.Table)
    def render_table(obj: "pa.Table", budget: int) -> str:
        native = native_repr_if_fits(obj, budget)
        if native is not None:
            return native

        columns = tuple(
            TableColumn(field.name, str(field.type)) for field in obj.schema
        )
        return render_table_summary("Table", len(obj), columns, budget, render_child)

    @register(pa.ChunkedArray)
    def render_chunked_array(obj: "pa.ChunkedArray", budget: int) -> str:
        native = native_repr_if_fits(obj, budget)
        if native is not None:
            return native

        return render_array_summary(
            "ChunkedArray",
            len(obj),
            str(obj.type),
            len(obj),
            budget,
            render_child,
        )

    @register(pa.Array)
    def render_array(obj: "pa.Array", budget: int) -> str:
        return render_array_summary(
            "Array",
            len(obj),
            str(obj.type),
            len(obj),
            budget,
            render_child,
            value_at=lambda index: obj[index].as_py(),
        )
