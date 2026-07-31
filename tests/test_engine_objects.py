"""Structured object and customization contracts for the private engine."""

import collections
import dataclasses

import reprobate
from reprobate._engine import render


def test_dataclass_complete_output_uses_record_syntax():
    @dataclasses.dataclass
    class User:
        name: str
        age: int

    value = User("alice", 30)

    assert render(value, 100, inference="off") == "User(name='alice', age=30)"


def test_dataclass_omits_repr_false_fields():
    @dataclasses.dataclass
    class Secret:
        visible: int
        hidden: int = dataclasses.field(repr=False)

    result = render(Secret(1, 2), 100, inference="off")

    assert result == "Secret(visible=1)"


def test_namedtuple_uses_field_names_instead_of_tuple_syntax():
    Point = collections.namedtuple("Point", ["x", "y"])

    assert render(Point(1, 2), 100, inference="off") == "Point(x=1, y=2)"


def test_public_object_attributes_are_rendered():
    class Job:
        def __init__(self):
            self.status = "running"
            self._secret = "hidden"

    assert render(Job(), 100, inference="off") == "Job(status='running')"


def test_inherited_and_string_slots_are_rendered():
    class Base:
        __slots__ = "base"

    class Child(Base):
        __slots__ = ("child",)

        def __init__(self):
            self.base = 1
            self.child = 2

    assert render(Child(), 100, inference="off") == "Child(base=1, child=2)"


def test_self_referencing_object_uses_cycle_marker():
    class Node:
        def __init__(self):
            self.child = self

    assert render(Node(), 100, inference="off") == "Node(child=<...>)"


def test_registered_renderer_can_recurse_through_public_render_child():
    class Box:
        def __init__(self, value):
            self.value = value

    @reprobate.register(Box)
    def render_box(obj, budget):
        inner = reprobate.render_child(obj.value, budget - 5)
        return f"Box({inner})"

    value = Box(["x" * 100 for _ in range(1_000)])

    assert render(value, 30) == "Box(<list[str](1000)>)"


def test_protocol_takes_precedence_over_registered_renderer():
    class Customized:
        def __budget_repr__(self, budget):
            return "protocol"[:budget]

    @reprobate.register(Customized)
    def render_customized(obj, budget):
        return "registry"[:budget]

    assert render(Customized(), 100) == "protocol"


def test_registered_renderer_can_use_public_render_attrs():
    class Model:
        def __init__(self):
            self.name = "alice"
            self.values = list(range(100))

    @reprobate.register(Model)
    def render_model(obj, budget):
        return reprobate.render_attrs(
            {"name": obj.name, "values": obj.values},
            "Model",
            budget,
        )

    result = render(Model(), 50, inference="off")

    assert result.startswith("Model(")
    assert "name='alice'" in result
    assert len(result) <= 50


def test_custom_renderer_cycle_uses_active_session_state():
    class Recursive:
        pass

    @reprobate.register(Recursive)
    def render_recursive(obj, budget):
        return f"Recursive({reprobate.render_child(obj, budget - 11)})"

    assert render(Recursive(), 100) == "Recursive(<...>)"


def test_custom_renderer_line_breaks_are_escaped():
    class Multiline:
        def __budget_repr__(self, budget):
            return "first\nsecond"

    assert render(Multiline(), 100) == "first\\nsecond"


def test_every_dataclass_budget_is_respected():
    @dataclasses.dataclass
    class Payload:
        status: str
        values: list[int]
        metadata: dict[str, str]

    value = Payload("ok", list(range(100)), {"source": "tool"})

    for budget in range(120):
        assert len(render(value, budget, inference="off")) <= budget
