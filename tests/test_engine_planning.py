"""Layer-planning and sibling allocation contracts."""

import dataclasses

import reprobate
from reprobate._engine import render
from reprobate._engine.planning import allocate_even


def test_even_allocator_redistributes_finite_unused_demand():
    assert allocate_even([20, 2, 30], 30) == [14, 2, 14]


def test_even_allocator_supports_open_ended_demand():
    assert allocate_even([None, 2, None], 30) == [14, 2, 14]


def test_even_allocator_returns_all_space_from_saturated_siblings():
    assert allocate_even([None, 0, 0], 30) == [30, 0, 0]


def test_even_mapping_redistributes_space_from_later_complete_sibling():
    early_large = {"large": "E" * 200, "done": "x"}
    late_large = {"done": "x", "large": "E" * 200}

    early_result = render(early_large, 60, policy="even", inference="off")
    late_result = render(late_large, 60, policy="even", inference="off")

    assert early_result.count("E") == late_result.count("E")
    assert len(early_result) > 50


def test_even_mapping_reclaims_space_from_shorter_complete_child():
    early_large = {"large": "E" * 200, "empty": []}
    late_large = {"empty": [], "large": "E" * 200}

    early_result = render(early_large, 60, policy="even", inference="off")
    late_result = render(late_large, 60, policy="even", inference="off")

    assert early_result.count("E") == late_result.count("E")
    assert "'empty': []" in early_result


def test_even_record_redistributes_space_from_complete_field():
    @dataclasses.dataclass
    class Payload:
        large: str
        done: str

    result = render(Payload("E" * 200, "x"), 60, policy="even", inference="off")

    assert result.count("E") > 15
    assert "done='x'" in result


def test_greedy_output_is_unchanged_by_even_layer_planning():
    value = {"large": "E" * 200, "done": "x"}

    assert render(value, 60, policy="greedy", inference="off") == (
        "{'large': <str(200): 'EEEEEEEEEEEEEEEEEEE...'>, 'done': 'x'}"
    )


def test_even_planning_does_not_probe_opaque_renderers_for_demand():
    calls = 0

    class Opaque:
        pass

    @reprobate.register(Opaque)
    def render_opaque(_value, budget):
        nonlocal calls
        calls += 1
        return "opaque-detail"[:budget]

    result = render(
        {"opaque": Opaque(), "done": "x"},
        60,
        policy="even",
        inference="off",
    )

    assert "opaque-detail" in result
    assert calls == 1


def test_even_layer_probes_share_a_budget_proportional_to_output():
    class TrackingList(list):
        def __init__(self):
            super().__init__([0] * 10_000)
            self.reads = 0

        def __iter__(self):
            for value in super().__iter__():
                self.reads += 1
                yield value

    children = [TrackingList() for _ in range(50)]

    result = render(children, 400, policy="even", inference="off")

    assert len(result) <= 400
    assert sum(child.reads for child in children) <= 2_000
