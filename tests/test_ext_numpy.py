"""Tests for numpy extension."""

import pytest

np = pytest.importorskip("numpy")

import reprobate


class TestNdarray:
    def test_small_array(self):
        arr = np.array([1, 2, 3])
        r = reprobate.render(arr, 200)
        assert "ndarray" in r
        assert "3" in r  # shape
        assert "1" in r  # values visible

    def test_multidimensional_shape(self):
        arr = np.zeros((2, 3, 4))
        r = reprobate.render(arr, 200)
        assert "2x3x4" in r
        assert "float64" in r

    def test_large_array_truncation(self):
        arr = np.arange(1000)
        r = reprobate.render(arr, 60)
        assert len(r) <= 60
        assert "ndarray" in r
        assert "more" in r

    def test_budget_respected(self):
        arr = np.arange(100)
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(arr, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
