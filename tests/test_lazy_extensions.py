"""Optional renderers register themselves on first use.

Importing reprobate imports none of the libraries it can render: a
library's renderers are registered the first time an object of one of its
types is rendered, when the library is necessarily loaded already. Each
case runs in a fresh interpreter, so nothing another test imported or
registered is in place.
"""

import subprocess
import sys
import textwrap

import pytest

LIBRARIES = ("numpy", "pandas", "pyarrow", "polars", "PIL", "pydantic")


def _run(code: str) -> str:
    done = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_importing_reprobate_imports_no_optional_library():
    out = _run(
        f"""
        import sys
        import reprobate
        print([m for m in {LIBRARIES!r} if m in sys.modules])
        """
    )
    assert out == "[]"


def test_a_dataframe_rendered_first_gets_its_renderer():
    pytest.importorskip("pandas")
    out = _run(
        """
        import pandas as pd
        import reprobate
        print(reprobate.render(pd.DataFrame({"a": list(range(100))}), 60))
        """
    )
    assert out.startswith("DataFrame(100x1, {'a': int64}")


def test_a_numpy_scalar_rendered_first_converts_to_its_builtin():
    """The scalar conversion is a registration too, looked up on its own."""
    pytest.importorskip("numpy")
    out = _run(
        """
        import numpy as np
        import reprobate
        print(reprobate.render(np.int64(3), 20))
        """
    )
    assert out == "3"


def test_a_subclass_defined_elsewhere_reaches_its_librarys_renderer():
    """A user's pydantic model lives in the user's module; the library is
    found through the class's MRO."""
    pytest.importorskip("pydantic")
    out = _run(
        """
        import pydantic
        import reprobate

        class User(pydantic.BaseModel):
            name: str
            age: int

        print(reprobate.render(User(name="ada", age=36), 80))
        """
    )
    assert out == "User(name='ada', age=36)"


def test_an_install_that_fails_leaves_generic_rendering():
    out = _run(
        """
        import reprobate
        from reprobate.registry import register_lazy

        calls = []

        def broken():
            calls.append(1)
            raise ImportError("not here")

        register_lazy("fakelib", broken)
        Thing = type("Thing", (), {"__module__": "fakelib.things"})
        first = reprobate.render([Thing()], 60)
        second = reprobate.render([Thing()], 60)
        print(first == second, len(calls))
        """
    )
    assert out == "True 1"
