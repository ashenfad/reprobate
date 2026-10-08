"""Optional renderer for PyArrow objects."""

try:
    import pyarrow as pa
except ImportError:
    pa = None

from ._engine.summaries import (
    TableColumn,
    one_line_native_repr,
    render_array_summary,
    render_table_summary,
)
from .core import render_child
from .registry import register

if pa is not None:

    @register(pa.Table)
    def render_table(obj: "pa.Table", budget: int) -> str:
        native = one_line_native_repr(obj, budget)
        if native is not None:
            return native

        columns = tuple(
            TableColumn(field.name, str(field.type)) for field in obj.schema
        )
        return render_table_summary(
            "Table",
            len(obj),
            columns,
            budget,
            render_child,
            row_at=lambda index: tuple(column[index].as_py() for column in obj.columns),
        )

    @register(pa.ChunkedArray)
    def render_chunked_array(obj: "pa.ChunkedArray", budget: int) -> str:
        native = one_line_native_repr(obj, budget)
        if native is not None:
            return native

        return render_array_summary(
            "ChunkedArray",
            len(obj),
            str(obj.type),
            len(obj),
            budget,
            render_child,
            value_at=lambda index: obj[index].as_py(),
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
