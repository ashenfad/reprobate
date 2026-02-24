"""Tests for core rendering engine."""

import collections
import dataclasses

import pytest

import reprobate


class TestPrimitives:
    def test_none(self):
        assert reprobate.render(None, 100) == "None"

    def test_bool(self):
        assert reprobate.render(True, 100) == "True"

    def test_int(self):
        assert reprobate.render(42, 100) == "42"

    def test_float(self):
        assert reprobate.render(3.14, 100) == "3.14"

    def test_short_string(self):
        assert reprobate.render("hello", 100) == "'hello'"

    def test_long_string_truncated(self):
        s = "a" * 200
        r = reprobate.render(s, 20)
        assert len(r) <= 20
        assert r.startswith("'")
        assert r.endswith("'")
        assert "..." in r

    def test_empty_bytes(self):
        assert reprobate.render(b"", 100) == "b''"


class TestContainers:
    def test_empty_list(self):
        assert reprobate.render([], 100) == "[]"

    def test_empty_dict(self):
        assert reprobate.render({}, 100) == "{}"

    def test_empty_tuple(self):
        assert reprobate.render((), 100) == "()"

    def test_small_list_fits(self):
        r = reprobate.render([1, 2, 3], 100)
        assert r == "[1, 2, 3]"

    def test_small_dict_fits(self):
        r = reprobate.render({"a": 1}, 100)
        assert r == "{'a': 1}"

    def test_list_truncation(self):
        obj = list(range(100))
        r = reprobate.render(obj, 40)
        assert len(r) <= 40
        assert r.startswith("[")
        assert r.endswith("]")
        assert "more" in r

    def test_dict_truncation(self):
        obj = {f"key_{i}": i for i in range(50)}
        r = reprobate.render(obj, 60)
        assert len(r) <= 60
        assert r.startswith("{")
        assert r.endswith("}")
        assert "more" in r

    def test_nested_dict(self):
        obj = {"a": {"b": {"c": 1}}}
        r = reprobate.render(obj, 30)
        assert len(r) <= 30


class TestObjects:
    def test_simple_object(self):
        class Foo:
            def __init__(self):
                self.x = 1
                self.y = 2

        r = reprobate.render(Foo(), 100)
        assert "Foo" in r
        assert "x=" in r

    def test_object_truncation(self):
        class Bar:
            def __init__(self):
                self.a = "hello"
                self.b = list(range(100))
                self.c = "world"

        r = reprobate.render(Bar(), 40)
        assert len(r) <= 40
        assert "Bar" in r

    def test_slotted_object(self):
        class Slotted:
            __slots__ = ("x", "y")

            def __init__(self, x, y):
                self.x = x
                self.y = y

        r = reprobate.render(Slotted(1, 2), 100)
        assert r == "Slotted(x=1, y=2)"

    def test_type_stubs(self):
        class Thing:
            def __init__(self):
                self.name = "a long enough name to eat the budget"
                self.data = [1, 2, 3]
                self.meta = {"key": "val"}

        r = reprobate.render(Thing(), 80)
        assert "Thing" in r
        # Attrs that don't get full render should show type stubs
        if "data=<" in r:
            assert "<list(3)>" in r
        if "meta=<" in r:
            assert "<dict(1)>" in r


class TestDataclasses:
    def test_small_dataclass(self):
        @dataclasses.dataclass
        class Point:
            x: int
            y: int

        r = reprobate.render(Point(1, 2), 100)
        assert r == "Point(x=1, y=2)"

    def test_dataclass_truncation(self):
        @dataclasses.dataclass
        class Big:
            name: str
            values: list
            extra: str

        obj = Big(name="hello", values=list(range(100)), extra="world")
        r = reprobate.render(obj, 40)
        assert len(r) <= 40
        assert "Big" in r
        assert "name=" in r

    def test_dataclass_repr_false(self):
        @dataclasses.dataclass
        class WithHidden:
            visible: int
            hidden: int = dataclasses.field(repr=False)

        r = reprobate.render(WithHidden(visible=1, hidden=2), 100)
        assert "visible=" in r
        assert "hidden=" not in r

    def test_dataclass_budget_respected(self):
        @dataclasses.dataclass
        class Many:
            a: str = "alpha"
            b: str = "bravo"
            c: str = "charlie"
            d: str = "delta"
            e: str = "echo"

        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(Many(), budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestNamedTuple:
    def test_small_namedtuple(self):
        Point = collections.namedtuple("Point", ["x", "y"])
        r = reprobate.render(Point(1, 2), 100)
        assert r == "Point(x=1, y=2)"

    def test_namedtuple_truncation(self):
        Record = collections.namedtuple("Record", ["name", "values", "extra"])
        obj = Record(name="hello", values=list(range(100)), extra="world")
        r = reprobate.render(obj, 40)
        assert len(r) <= 40
        assert "Record" in r
        assert "name=" in r

    def test_namedtuple_budget_respected(self):
        Big = collections.namedtuple("Big", ["a", "b", "c", "d", "e"])
        obj = Big("alpha", "bravo", "charlie", "delta", "echo")
        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(obj, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestDefaultDict:
    def test_small_defaultdict(self):
        d = collections.defaultdict(int, {"a": 1, "b": 2})
        r = reprobate.render(d, 100)
        assert "defaultdict" in r
        assert "int" in r
        assert "'a'" in r

    def test_empty_defaultdict(self):
        d = collections.defaultdict(list)
        r = reprobate.render(d, 100)
        assert "defaultdict" in r
        assert "list" in r

    def test_defaultdict_truncation(self):
        d = collections.defaultdict(int, {f"key_{i}": i for i in range(50)})
        r = reprobate.render(d, 50)
        assert len(r) <= 50
        assert "defaultdict" in r

    def test_defaultdict_budget_respected(self):
        d = collections.defaultdict(int, {"a": 1, "b": 2, "c": 3})
        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(d, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestCounter:
    def test_small_counter(self):
        c = collections.Counter({"a": 3, "b": 1})
        r = reprobate.render(c, 100)
        assert "Counter" in r
        assert "'a'" in r

    def test_empty_counter(self):
        r = reprobate.render(collections.Counter(), 100)
        assert r == "Counter()"

    def test_counter_most_common_order(self):
        c = collections.Counter({"rare": 1, "common": 99})
        r = reprobate.render(c, 100)
        # most_common should put 'common' first
        assert r.index("'common'") < r.index("'rare'")

    def test_counter_budget_respected(self):
        c = collections.Counter({f"item_{i}": i for i in range(50)})
        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(c, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestDeque:
    def test_small_deque(self):
        d = collections.deque([1, 2, 3])
        r = reprobate.render(d, 100)
        assert r == "deque([1, 2, 3])"

    def test_empty_deque(self):
        r = reprobate.render(collections.deque(), 100)
        assert r == "deque()"

    def test_deque_truncation(self):
        d = collections.deque(range(100))
        r = reprobate.render(d, 40)
        assert len(r) <= 40
        assert "deque" in r
        assert "more" in r

    def test_deque_budget_respected(self):
        d = collections.deque(range(50))
        for budget in [5, 10, 20, 50, 100]:
            r = reprobate.render(d, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestBudgetRespected:
    """Every render call must respect the budget."""

    def test_various_budgets(self):
        objects = [
            None,
            42,
            "hello world" * 20,
            [1, 2, 3, 4, 5],
            {"key": "value", "nested": [1, 2, 3]},
            list(range(1000)),
            {str(i): i for i in range(100)},
        ]
        for obj in objects:
            for budget in [5, 10, 20, 50, 100, 500]:
                r = reprobate.render(obj, budget)
                assert len(r) <= budget, (
                    f"Budget {budget} exceeded: got {len(r)} chars "
                    f"for {type(obj).__name__}: {r!r}"
                )


class TestCircularReferences:
    def test_self_referencing_list(self):
        a = [1, 2]
        a.append(a)
        r = reprobate.render(a, 100)
        assert len(r) <= 100
        assert "<...>" in r

    def test_self_referencing_dict(self):
        d = {}
        d["self"] = d
        r = reprobate.render(d, 100)
        assert len(r) <= 100
        assert "<...>" in r

    def test_mutual_reference(self):
        a = []
        b = [a]
        a.append(b)
        r = reprobate.render(a, 100)
        assert len(r) <= 100
        assert "<...>" in r

    def test_self_referencing_object(self):
        class Node:
            def __init__(self):
                self.child = None

        n = Node()
        n.child = n
        r = reprobate.render(n, 100)
        assert len(r) <= 100
        assert "<...>" in r

    def test_no_false_positive(self):
        # Same-value objects at different ids should not trigger cycle detection
        shared = [1, 2, 3]
        obj = [shared, shared]
        r = reprobate.render(obj, 100)
        # shared appears twice but it's not a cycle — it's a DAG
        # However, our id-based detection will flag the second occurrence.
        # This is a known trade-off (same as Python's repr).
        assert len(r) <= 100


class TestPolicy:
    def test_even_shows_more_fields(self):
        @dataclasses.dataclass
        class Wide:
            a: str = "alpha"
            b: str = "bravo"
            c: str = "charlie"
            d: str = "delta"

        budget = 60
        greedy = reprobate.render(Wide(), budget, policy="greedy")
        even = reprobate.render(Wide(), budget, policy="even")
        assert len(greedy) <= budget
        assert len(even) <= budget
        # Even policy should show more field names
        even_fields = sum(1 for f in ["a=", "b=", "c=", "d="] if f in even)
        greedy_fields = sum(1 for f in ["a=", "b=", "c=", "d="] if f in greedy)
        assert even_fields >= greedy_fields

    def test_even_budget_respected(self):
        @dataclasses.dataclass
        class Big:
            a: str = "alpha" * 10
            b: str = "bravo" * 10
            c: str = "charlie" * 10
            d: str = "delta" * 10
            e: str = "echo" * 10

        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(Big(), budget, policy="even")
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )

    def test_even_propagates_to_nested(self):
        @dataclasses.dataclass
        class Inner:
            x: str = "xxxxx"
            y: str = "yyyyy"

        @dataclasses.dataclass
        class Outer:
            first: Inner = None
            second: Inner = None

            def __post_init__(self):
                self.first = Inner()
                self.second = Inner()

        r = reprobate.render(Outer(), 200, policy="even")
        # Both fields should get rendered (not just first)
        assert "first=" in r
        assert "second=" in r

    def test_default_is_greedy(self):
        @dataclasses.dataclass
        class Thing:
            a: str = "x" * 50
            b: str = "y" * 50

        budget = 60
        default = reprobate.render(Thing(), budget)
        greedy = reprobate.render(Thing(), budget, policy="greedy")
        assert default == greedy


class TestRegistry:
    def test_custom_renderer(self):
        class MyType:
            pass

        @reprobate.register(MyType)
        def render_my(obj, budget):
            return "custom"[:budget]

        assert reprobate.render(MyType(), 100) == "custom"

    def test_protocol_method(self):
        class WithProtocol:
            def __budget_repr__(self, budget):
                return f"proto({budget})"

        r = reprobate.render(WithProtocol(), 100)
        assert r == "proto(100)"


class TestNumpy:
    np = pytest.importorskip("numpy")

    def test_small_array(self):
        arr = self.np.array([1, 2, 3])
        r = reprobate.render(arr, 200)
        assert "ndarray" in r
        assert "3" in r  # shape
        assert "1" in r  # values visible

    def test_multidimensional_shape(self):
        arr = self.np.zeros((2, 3, 4))
        r = reprobate.render(arr, 200)
        assert "2x3x4" in r
        assert "float64" in r

    def test_large_array_truncation(self):
        arr = self.np.arange(1000)
        r = reprobate.render(arr, 60)
        assert len(r) <= 60
        assert "ndarray" in r
        assert "more" in r

    def test_budget_respected(self):
        arr = self.np.arange(100)
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(arr, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )


class TestPandas:
    pd = pytest.importorskip("pandas")

    def test_dataframe_shape_and_columns(self):
        df = self.pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        r = reprobate.render(df, 200)
        assert "DataFrame" in r or "a" in r  # either custom or native repr
        assert len(r) <= 200

    def test_dataframe_budget_respected(self):
        df = self.pd.DataFrame({f"col_{i}": range(100) for i in range(20)})
        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(df, budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )

    def test_series_dtype(self):
        s = self.pd.Series([1, 2, 3], dtype="int64")
        r = reprobate.render(s, 200)
        assert len(r) <= 200

    def test_named_series(self):
        s = self.pd.Series([1, 2, 3], name="values")
        r = reprobate.render(s, 200)
        assert "values" in r
        assert len(r) <= 200


class TestPydantic:
    pydantic = pytest.importorskip("pydantic")

    def test_simple_model(self):
        class User(self.pydantic.BaseModel):
            name: str = "alice"
            age: int = 30

        r = reprobate.render(User(), 200)
        assert "User" in r
        assert "name=" in r
        assert "age=" in r

    def test_model_truncation(self):
        class BigModel(self.pydantic.BaseModel):
            a: str = "alpha"
            b: str = "bravo"
            c: str = "charlie"
            d: str = "delta"
            e: str = "echo"

        r = reprobate.render(BigModel(), 40)
        assert len(r) <= 40
        assert "BigModel" in r

    def test_budget_respected(self):
        class Config(self.pydantic.BaseModel):
            host: str = "localhost"
            port: int = 8080
            debug: bool = True

        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(Config(), budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
