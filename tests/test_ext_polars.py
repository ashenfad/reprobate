"""Tests for polars extension."""

import pytest

pl = pytest.importorskip("polars")

import reprobate  # noqa: E402


class TestDataFrame:
    def test_small_uses_native_repr(self):
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        r = reprobate.render(df, 200)
        assert r == repr(df).replace("\n", "\\n")

    def test_compact_fallback(self):
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        r = reprobate.render(df, 60)
        assert "DataFrame" in r
        assert "2x2" in r
        assert "'a'" in r
        assert "'b'" in r

    def test_many_columns_truncation(self):
        df = pl.DataFrame({f"col_{i}": range(5) for i in range(20)})
        r = reprobate.render(df, 80)
        assert len(r) <= 80
        assert "DataFrame" in r
        assert "5x20" in r
        assert "more" in r

    def test_compact_fallback_includes_column_dtypes(self):
        df = pl.DataFrame(
            {"user_id": range(100), "name": [f"user_{i}" for i in range(100)]}
        )

        r = reprobate.render(df, 80)

        assert "'user_id': Int64" in r
        assert "'name': String" in r

    def test_budget_respected(self):
        df = pl.DataFrame({f"col_{i}": range(100) for i in range(20)})
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(df, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestSeries:
    def test_series(self):
        s = pl.Series("vals", [1, 2, 3])
        r = reprobate.render(s, 200)
        assert "Series" in r
        assert "3" in r
        assert "vals" in r

    def test_budget_respected(self):
        s = pl.Series("vals", range(1000))
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(s, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
