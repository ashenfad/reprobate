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

    def test_values_render_as_builtins(self):
        r = reprobate.render(np.arange(6).reshape(2, 3), 200)
        assert r == "ndarray(2x3, int64, [0, 1, 2, 3, 4, 5])"

    def test_reduced_precision_values_keep_their_short_spelling(self):
        r = reprobate.render(np.array([0.1, np.nan], dtype=np.float32), 200)
        assert r == "ndarray(2, float32, [0.1, nan])"


class TestScalars:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (np.int64(3), "3"),
            (np.uint8(255), "255"),
            (np.float64(1.5), "1.5"),
            (np.float32(0.1), "0.1"),
            (np.float16(0.1), "0.1"),
            (np.complex64(1 + 2j), "(1+2j)"),
            (np.bool_(True), "True"),
            (np.str_("a"), "'a'"),
            (np.bytes_(b"x"), "b'x'"),
        ],
    )
    def test_scalar_renders_as_builtin(self, value, expected):
        assert reprobate.render(value, 50) == expected

    def test_scalars_inside_containers(self):
        assert reprobate.render({"n": np.int64(3)}, 50) == "{'n': 3}"

    def test_scalar_containers_match_builtin_density(self):
        values = [np.int64(i) for i in range(100)]
        assert reprobate.render(values, 60) == reprobate.render(list(range(100)), 60)

    def test_uniform_scalars_collapse(self):
        values = [np.float64(0.0) for _ in range(97)]
        assert reprobate.render(values, 60) == "[0.0] * 97"

    def test_mixed_scalar_types_do_not_collapse(self):
        values = [np.float64(0.5), np.float32(0.5)] * 20
        assert "*" not in reprobate.render(values, 60)

    def test_scalars_without_builtin_equivalent_keep_their_repr(self):
        value = np.datetime64("2024-01-01")
        assert reprobate.render(value, 50) == repr(value)

    @pytest.mark.parametrize("unit", ["s", "ns"])
    def test_timedelta_keeps_its_unit(self, unit):
        # timedelta64 subclasses signedinteger, and int() of a nanosecond
        # timedelta silently drops the unit.
        value = np.timedelta64(5, unit)
        assert reprobate.render(value, 50) == repr(value)

    def test_subclass_with_own_repr_is_not_converted(self):
        class Tagged(np.float64):
            def __repr__(self):
                return f"Tagged({float(self)})"

        assert reprobate.render([Tagged(1.0)], 50) == "[Tagged(1.0)]"

    def test_subclass_is_not_converted_on_its_ancestors_behalf(self):
        class Plain(np.int64):
            pass

        value = Plain(3)
        assert reprobate.render(value, 50) == repr(value)

    def test_registered_renderer_takes_precedence(self):
        class Tagged(np.float64):
            pass

        @reprobate.register(Tagged)
        def render_tagged(obj, budget):
            return "tagged"[:budget]

        assert reprobate.render([Tagged(1.0)], 50) == "[tagged]"
