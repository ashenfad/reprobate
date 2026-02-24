"""Optional renderer for PyArrow objects."""

try:
    import pyarrow as pa
except ImportError:
    pa = None

from .core import render_child
from .registry import register

if pa is not None:

    @register(pa.Table)
    def render_table(obj: "pa.Table", budget: int) -> str:
        try:
            r = repr(obj)
            if len(r) <= budget:
                return r
        except Exception:
            pass

        rows, cols = obj.shape
        col_names = obj.column_names
        header = f"Table({rows}x{cols}"

        if budget <= len(header) + 1:
            return f"Table({rows}x{cols})"[:budget]

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

    @register(pa.ChunkedArray)
    def render_chunked_array(obj: "pa.ChunkedArray", budget: int) -> str:
        try:
            r = repr(obj)
            if len(r) <= budget:
                return r
        except Exception:
            pass

        dtype = str(obj.type)
        n = len(obj)
        header = f"ChunkedArray({n}, {dtype})"
        return header[:budget]

    @register(pa.Array)
    def render_array(obj: "pa.Array", budget: int) -> str:
        dtype = str(obj.type)
        n = len(obj)
        header = f"Array({n}, {dtype}"

        if budget <= len(header) + 1:
            return f"Array({n}, {dtype})"[:budget]

        remaining = budget - len(header) - 5  # ", [" before data, "])" at end
        if remaining < 5:
            return (header + ")")[:budget]

        # Peek at values
        peek_parts: list[str] = []
        used = 0
        limit = min(n, 20)

        for i in range(limit):
            sep = 2 if peek_parts else 0
            omitted = n - i - 1
            reserve = len(f", ...{omitted} more") if omitted > 0 else 0
            avail = remaining - used - sep - reserve

            val = obj[i].as_py()
            r = render_child(val, avail)
            if len(r) > avail or avail < 5:
                break
            peek_parts.append(r)
            used += len(r) + sep

        omitted = n - len(peek_parts)
        if omitted > 0:
            peek_parts.append(f"...{omitted} more")

        return header + ", [" + ", ".join(peek_parts) + "])"
