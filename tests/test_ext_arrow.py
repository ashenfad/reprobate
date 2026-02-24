"""Tests for PyArrow extension."""

import pytest

pa = pytest.importorskip("pyarrow")

import reprobate


class TestTable:
    def test_small_uses_native_repr(self):
        table = pa.table({"a": [1, 2], "b": [3, 4]})
        r = reprobate.render(table, 500)
        assert r == repr(table)

    def test_compact_fallback(self):
        table = pa.table({f"col_{i}": range(100) for i in range(10)})
        r = reprobate.render(table, 80)
        assert "Table" in r
        assert "100x10" in r

    def test_budget_respected(self):
        table = pa.table({f"col_{i}": range(100) for i in range(10)})
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(table, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestArray:
    def test_values(self):
        arr = pa.array([1, 2, 3])
        r = reprobate.render(arr, 200)
        assert "Array" in r
        assert "int64" in r
        assert "1" in r

    def test_truncation(self):
        arr = pa.array(range(1000))
        r = reprobate.render(arr, 60)
        assert len(r) <= 60
        assert "Array" in r
        assert "more" in r

    def test_budget_respected(self):
        arr = pa.array(range(100))
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(arr, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestChunkedArray:
    def test_small_uses_native_repr(self):
        chunked = pa.chunked_array([[1, 2], [3, 4]])
        r = reprobate.render(chunked, 500)
        assert r == repr(chunked)

    def test_compact_fallback(self):
        chunked = pa.chunked_array([list(range(1000))])
        r = reprobate.render(chunked, 40)
        assert "ChunkedArray" in r
        assert "int64" in r

    def test_budget_respected(self):
        chunked = pa.chunked_array([list(range(1000))])
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(chunked, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
