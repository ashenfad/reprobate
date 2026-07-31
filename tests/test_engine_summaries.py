"""Contracts for shared optional-extension semantic summaries."""

from reprobate._engine.summaries import (
    TableColumn,
    native_repr_if_fits,
    render_array_summary,
    render_table_summary,
)


def render_value(value: object, budget: int) -> str:
    return repr(value)[:budget]


def test_table_summary_pairs_column_names_with_authoritative_types():
    columns = (
        TableColumn("users", "list<string>"),
        TableColumn("cursor", "string"),
    )

    result = render_table_summary("Table", 200, columns, 100, render_value)

    assert result == "Table(200x2, {'users': list<string>, 'cursor': string})"


def test_table_summary_omits_details_instead_of_clipping_column_names():
    columns = (TableColumn("a_long_column_name", "int64"),)

    result = render_table_summary("Table", 10, columns, 11, render_value)

    assert result == "Table(10x1)"


def test_table_summary_preserves_an_omission_count():
    columns = tuple(TableColumn(f"column_{index}", "int64") for index in range(20))

    result = render_table_summary("Table", 5, columns, 60, render_value)

    assert result.startswith("Table(5x20, {'column_0': int64")
    assert "...19 more" in result
    assert len(result) <= 60


def test_array_summary_shows_shape_type_and_values():
    values = list(range(100))

    result = render_array_summary(
        "Array",
        (10, 10),
        "int64",
        len(values),
        60,
        render_value,
        value_at=values.__getitem__,
    )

    assert result.startswith("Array(10x10, int64, [0, 1")
    assert "more" in result
    assert len(result) <= 60


def test_array_summary_does_not_present_an_ellipsis_as_a_value():
    result = render_array_summary(
        "Array",
        100,
        "large_scalar",
        100,
        35,
        lambda _value, _budget: "...",
        value_at=lambda index: index,
    )

    assert result == "Array(100, large_scalar)"


def test_scalar_array_shape_is_explicit():
    result = render_array_summary(
        "ndarray",
        (),
        "float64",
        1,
        40,
        render_value,
        value_at=lambda _index: 1.0,
    )

    assert result == "ndarray(scalar, float64, [1.0])"


def test_native_repr_budget_applies_after_newline_normalization():
    class Multiline:
        def __repr__(self) -> str:
            return "a\nb"

    assert native_repr_if_fits(Multiline(), 3) is None
    assert native_repr_if_fits(Multiline(), 4) == "a\\nb"


def test_summary_helpers_respect_every_small_budget():
    columns = tuple(TableColumn(f"column_{index}", "int64") for index in range(20))
    values = list(range(100))

    for budget in range(101):
        table = render_table_summary("Table", 100, columns, budget, render_value)
        array = render_array_summary(
            "Array",
            100,
            "int64",
            len(values),
            budget,
            render_value,
            value_at=values.__getitem__,
        )
        assert len(table) <= budget
        assert len(array) <= budget
