"""Bounded rendering of bytearray, memoryview and array.array values."""

import array
import re
import tracemalloc

import pytest

from reprobate._engine import render

LARGE = 50 << 20
# Python 3.13 deprecates the "u" typecode in favor of "w".
UNICODE = "w" if "w" in array.typecodes else "u"


def _peak_while_rendering(value, budget):
    tracemalloc.start()
    try:
        result = render(value, budget)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, peak


@pytest.mark.parametrize(
    ("make", "expected_prefix"),
    [
        (lambda: bytearray(LARGE), f"<bytearray({LARGE}): b'\\x00\\x00"),
        (lambda: memoryview(bytearray(LARGE)), f"<memoryview({LARGE}): b'\\x00\\x00"),
        (lambda: array.array("B", bytes(LARGE)), f"<array[B]({LARGE}): 0, 0, 0"),
    ],
    ids=["bytearray", "memoryview", "array"],
)
def test_large_buffer_renders_a_sized_preview_without_building_its_repr(
    make, expected_prefix
):
    value = make()

    result, peak = _peak_while_rendering(value, 2000)

    assert peak < 1 << 20
    assert len(result) <= 2000
    assert result.startswith(expected_prefix)
    assert result.endswith("...'>") or result.endswith(", ...>")


@pytest.mark.parametrize(
    "value",
    [
        bytearray(),
        bytearray(b"abc"),
        bytearray(b"quote ' and \" mix\n\x00\xff"),
        array.array("i", [1, -2, 3]),
        array.array("d", [0.5, 1e300]),
        array.array(UNICODE, "hey"),
        array.array("b"),
    ],
)
def test_small_buffer_renders_exactly_as_repr_when_it_fits(value):
    assert render(value, len(repr(value))) == repr(value)


def test_bytearray_subclass_keeps_its_own_name():
    class Buffer(bytearray):
        pass

    assert render(Buffer(b"ab"), 100) == "Buffer(b'ab')"
    assert render(Buffer(300), 60).startswith("<Buffer(300): b'\\x00")


def test_bytearray_subclass_custom_repr_is_honored():
    class Custom(bytearray):
        def __repr__(self):
            return "Custom!"

    assert render(Custom(b"ab"), 100) == "Custom!"


def test_bytearray_bare_preview_keeps_the_bytearray_spelling():
    result = render(bytearray(b"x" * 100), 25)

    assert re.fullmatch(r"bytearray\(b'x+\.\.\.'\)", result)


def test_bytearray_preview_does_not_change_bytes_previews():
    value = bytes(range(256))

    assert render(value, 20) == "b'\\x00\\x01\\x02...'"
    assert render(value, 40) == "<bytes(256): b'\\x00\\x01\\x02\\x03\\x04...'>"
    assert render(bytearray(value), 45) == (
        "<bytearray(256): b'\\x00\\x01\\x02\\x03\\x04...'>"
    )


def test_bytes_and_str_rendering_is_unchanged():
    assert render(bytes(LARGE), 40) == f"<bytes({LARGE}): b'\\x00\\x00\\x00...'>"
    assert render(b"ab'c\"" * 30, 20) == "b'ab\\'c\"ab\\'c\"ab...'"
    assert render("x" * 1000, 40) == "<str(1000): 'xxxxxxxxxxxxxxxxxxxxxx...'>"
    assert render([b"x" * 100, "y" * 100], 60) == (
        "[<bytes(100): b'xxxxxxxxxxxxxxxxxxxxxxxxxx...'>, <str(100)>]"
    )


def test_byte_memoryview_shows_its_contents():
    assert render(memoryview(b"hello"), 100) == "<memoryview(5): b'hello'>"
    assert render(memoryview(b"abcdef")[::2], 100) == "<memoryview(3): b'ace'>"
    assert render(memoryview(b"abc").cast("c"), 100) == "<memoryview(3): b'abc'>"


def test_long_byte_memoryview_shows_a_sized_preview():
    result = render(memoryview(b"x" * 300), 60)

    assert re.fullmatch(r"<memoryview\(300\): b'x+\.\.\.'>", result)
    assert len(result) <= 60


def test_non_byte_memoryview_renders_format_and_shape():
    numbers = memoryview(array.array("i", range(12)))

    assert render(numbers, 100) == "<memoryview[i](12)>"
    assert render(memoryview(bytes(12)).cast("B", (3, 4)), 100) == (
        "<memoryview[B](3, 4)>"
    )


def test_released_memoryview_renders_a_stub():
    view = memoryview(b"x")
    view.release()

    assert render(view, 100) == "<memoryview>"


def test_hashable_memoryview_key_renders_a_stub():
    assert render({memoryview(b"hello"): 1}, 100) == "{<memoryview(5)>: 1}"


def test_buffers_inside_containers_render_completely_when_they_fit():
    value = [bytearray(b"x"), array.array("b", [1])]

    assert render(value, 100) == repr(value)


def test_buffer_budgets_are_never_exceeded():
    class Buffer(bytearray):
        pass

    values = [
        bytearray(),
        bytearray(b"quote ' and \" mix\n\x00\xff" * 20),
        bytearray(5000),
        Buffer(b"abc" * 50),
        memoryview(b"q'\"" * 100),
        memoryview(bytes(range(256)))[::3],
        memoryview(array.array("d", range(50))),
        memoryview(bytes(24)).cast("B", (2, 3, 4)),
        array.array("d", [1 / 3] * 100),
        array.array(UNICODE, "spelled out" * 20),
        array.array("q", range(-500, 500)),
        [bytearray(b"ab" * 40)] * 30,
        {"payload": bytearray(1000), "view": memoryview(b"x" * 1000)},
    ]
    for value in values:
        for budget in range(0, 160):
            for inference in ("off", "best_effort"):
                result = render(value, budget, inference=inference)
                assert len(result) <= budget, (value, budget, result)


class _LenRaises(bytearray):
    def __len__(self):
        raise RuntimeError("len")


class _GetitemRaises(array.array):
    def __getitem__(self, index):
        raise RuntimeError("getitem")


@pytest.mark.parametrize(
    "value",
    [_LenRaises(b"abc"), _GetitemRaises("i", [1, 2, 3])],
    ids=["bytearray-len", "array-getitem"],
)
def test_a_subclass_overriding_what_the_preview_uses_renders_by_its_repr(value):
    """It keeps the base repr but not the base behaviour, so the buffer path
    would call its override; its own repr is rendered instead."""
    assert render(value, 200) == repr(value)


def _view_of_struct(fields):
    import ctypes

    struct = type("S", (ctypes.Structure,), {"_fields_": fields})
    return memoryview(struct())


def test_a_long_view_format_is_summarized_without_its_whole_text():
    import ctypes

    view = _view_of_struct([(f"field{i}", ctypes.c_int) for i in range(20_000)])
    assert len(view.format) > 100_000
    tracemalloc.start()
    try:
        rendered = render(view, 60)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert len(rendered) <= 60
    assert rendered.startswith("<memoryview[")
    # Reading the format allocates it once; building the summary around a
    # copy of it would allocate it again.
    assert peak < 1.5 * len(view.format)


def test_a_view_format_with_a_newline_stays_on_one_line():
    import ctypes

    view = _view_of_struct([("a\nb", ctypes.c_int)])
    assert "\n" in view.format
    rendered = render(view, 200)
    assert "\n" not in rendered
    assert "\\n" in rendered
