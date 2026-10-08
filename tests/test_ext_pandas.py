"""Tests for pandas extension."""

import pytest

pd = pytest.importorskip("pandas")
np = pytest.importorskip("numpy")

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

    def test_small_renders_rows_instead_of_escaped_native_repr(self):
        df = pd.DataFrame({"name": ["ada", "bo", "cy"], "score": [7, 2, 5]})

        r = reprobate.render(df, 600)

        # String columns are ``str`` in pandas 3 and ``object`` before it.
        assert r == (
            f"DataFrame(3x2, {{'name': {df.dtypes['name']}, 'score': int64}}, "
            "[('ada', 7), ('bo', 2), ('cy', 5)])"
        )

    def test_rows_follow_only_a_complete_schema(self):
        df = pd.DataFrame({f"col_{i}": range(5) for i in range(20)})

        r = reprobate.render(df, 80)

        assert "more}" in r
        assert r.endswith("})")

    def test_large_frame_shows_leading_rows(self):
        df = pd.DataFrame({"a": range(300), "b": range(300)})

        r = reprobate.render(df, 80)

        assert r.startswith("DataFrame(300x2, {'a': int64, 'b': int64}, [(0, 0), ")
        assert r.endswith("more])")
        assert len(r) <= 80

    def test_numpy_scalar_labels_count_as_complete(self):
        columns = pd.Index([np.int64(1), "b"], dtype=object)
        df = pd.DataFrame([[1, 2]], columns=columns)

        r = reprobate.render(df, 200)

        assert r == "DataFrame(1x2, {1: int64, 'b': int64}, [(1, 2)])"


class TestSeries:
    def test_numpy_scalar_name_counts_as_complete(self):
        s = pd.Series([1, 2], name=np.int64(5))
        assert reprobate.render(s, 200) == "Series(2, int64, name=5, [1, 2])"

    def test_values_render_as_builtins(self):
        s = pd.Series([1, 2, 3], dtype="int64", name="n")
        assert reprobate.render(s, 200) == "Series(3, int64, name='n', [1, 2, 3])"

    def test_dtype(self):
        s = pd.Series([1, 2, 3], dtype="int64")
        r = reprobate.render(s, 200)
        assert len(r) <= 200

    def test_named_series(self):
        s = pd.Series([1, 2, 3], name="values")
        r = reprobate.render(s, 200)
        assert "values" in r
        assert len(r) <= 200
