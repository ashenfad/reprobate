"""Tests for pandas extension."""

import pytest

pd = pytest.importorskip("pandas")

import reprobate  # noqa: E402


class TestDataFrame:
    def test_shape_and_columns(self):
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        r = reprobate.render(df, 200)
        assert "DataFrame" in r or "a" in r  # either custom or native repr
        assert len(r) <= 200

    def test_budget_respected(self):
        df = pd.DataFrame({f"col_{i}": range(100) for i in range(20)})
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(df, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )

    def test_compact_fallback_includes_column_dtypes(self):
        df = pd.DataFrame(
            {
                "user_id": pd.Series(range(100), dtype="int64"),
                "score": pd.Series(range(100), dtype="float64"),
            }
        )

        r = reprobate.render(df, 80, inference="off")

        assert "'user_id': int64" in r
        assert "'score': float64" in r


class TestSeries:
    def test_dtype(self):
        s = pd.Series([1, 2, 3], dtype="int64")
        r = reprobate.render(s, 200)
        assert len(r) <= 200

    def test_named_series(self):
        s = pd.Series([1, 2, 3], name="values")
        r = reprobate.render(s, 200)
        assert "values" in r
        assert len(r) <= 200
