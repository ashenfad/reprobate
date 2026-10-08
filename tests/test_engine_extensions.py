"""Optional renderer integration contracts for the private engine."""

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pl = pytest.importorskip("polars")
pa = pytest.importorskip("pyarrow")
Image = pytest.importorskip("PIL.Image")
pydantic = pytest.importorskip("pydantic")

from reprobate._engine import render  # noqa: E402


@pytest.mark.parametrize(
    ("value", "signals"),
    [
        (np.arange(100), ("ndarray", "int64")),
        (pd.DataFrame({"a": range(100), "b": range(100)}), ("DataFrame", "100x2")),
        (pd.Series(range(100), name="values"), ("Series", "int64")),
        (pl.DataFrame({"a": range(100), "b": range(100)}), ("DataFrame", "100x2")),
        (pl.Series("values", range(100)), ("Series", "Int64")),
        (pa.table({"a": range(100), "b": range(100)}), ("Table", "100x2")),
        (pa.array(range(100)), ("Array", "int64")),
        (Image.new("RGB", (640, 480)), ("Image", "640x480")),
    ],
)
def test_optional_renderer_summary(value, signals):
    result = render(value, 60)

    assert len(result) <= 60
    assert "\n" not in result
    assert all(signal in result for signal in signals)


def test_pydantic_renderer_uses_active_render_attrs_session():
    class Model(pydantic.BaseModel):
        name: str = "alice"
        values: list[int] = list(range(100))

    result = render(Model(), 60)

    assert result.startswith("Model(")
    assert "name='alice'" in result
    assert "values=[0, 1" in result
    assert "more" in result
    assert len(result) <= 60


@pytest.mark.parametrize(
    "value",
    [
        pd.DataFrame({"a": [1, 2], "b": [3, 4]}),
        pd.Series([1, 2, 3]),
        pl.DataFrame({"a": [1, 2], "b": [3, 4]}),
        pl.Series("values", [1, 2, 3]),
        pa.table({"a": [1, 2], "b": [3, 4]}),
        pa.chunked_array([[1, 2], [3]]),
    ],
)
def test_multiline_native_repr_yields_to_typed_summary(value):
    # Escaping a table repr onto one line destroys its alignment and spends
    # budget on escapes, even when the escaped form would fit.
    result = render(value, 600)

    assert "\\n" not in result
    assert "[1, 2, 3]" in result or "[(1, 3), (2, 4)]" in result
