"""Optional renderer for pandas objects."""

from ._engine.summaries import (
    TableColumn,
    one_line_native_repr,
    render_array_summary,
    render_table_summary,
)
from .core import render_child
from .registry import register, register_lazy


def install() -> None:
    """Register the pandas renderers.

    Run by the registry the first time it meets a pandas type: an
    object of that type exists, so pandas is already loaded and the
    import below costs nothing.
    """
    import pandas as pd

    @register(pd.DataFrame)
    def render_dataframe(obj: "pd.DataFrame", budget: int) -> str:
        native = one_line_native_repr(obj, budget)
        if native is not None:
            return native

        columns = tuple(
            TableColumn(name, str(dtype))
            for name, dtype in zip(obj.columns, obj.dtypes, strict=True)
        )
        return render_table_summary(
            "DataFrame",
            len(obj),
            columns,
            budget,
            render_child,
            row_at=lambda index: tuple(obj.iloc[index]),
        )

    @register(pd.Series)
    def render_series(obj: "pd.Series", budget: int) -> str:
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
            value_at=obj.iloc.__getitem__,
            metadata=metadata,
        )


register_lazy("pandas", install)
