"""Core collection contracts for the private replacement engine."""

import collections

import pytest

from reprobate._engine import render


@pytest.mark.parametrize(
    "value",
    [
        {"beta", "alpha", "gamma"},
        frozenset({1, 2, 3}),
        set(),
        frozenset(),
        collections.deque([1, 2, 3]),
        collections.deque([1, 2, 3], maxlen=5),
        collections.Counter({"rare": 1, "common": 99}),
        collections.defaultdict(int, {"a": 1, "b": 2}),
    ],
)
def test_complete_collection_output_matches_native_repr(value):
    expected = repr(value)

    assert render(value, len(expected), inference="off") == expected


@pytest.mark.parametrize(
    "value",
    [
        set(range(100)),
        frozenset(range(100)),
        collections.deque(range(100), maxlen=200),
        collections.Counter({f"item-{index}": index for index in range(100)}),
        collections.defaultdict(
            list, {f"item-{index}": [index] for index in range(100)}
        ),
    ],
)
def test_collection_wrappers_respect_every_small_budget(value):
    for budget in range(80):
        assert len(render(value, budget, inference="off")) <= budget


def test_set_output_uses_native_iteration_order():
    value = {"beta", "alpha", "gamma", "delta"}

    assert render(value, 1_000, inference="off") == repr(value)


def test_self_referencing_list_uses_circular_marker():
    value = []
    value.append(value)

    assert render(value, 100, inference="off") == "[<...>]"


def test_self_referencing_mapping_uses_circular_marker():
    value = {}
    value["self"] = value

    assert render(value, 100, inference="off") == "{'self': <...>}"


def test_uniform_sequences_collapse_to_product_expressions():
    assert render([0.0] * 97, 40) == "[0.0] * 97"
    assert render(("a",) * 50, 40) == "('a',) * 50"
    assert render(collections.deque([0.0] * 97), 40) == "deque([0.0] * 97)"
    assert render(["N/A"] * 100, 40, inference="off") == "['N/A'] * 100"


def test_identical_object_references_collapse_to_a_product_expression():
    shared = {"a": 1}

    assert render([shared] * 30, 40) == "[{'a': 1}] * 30"


def test_complete_render_outranks_the_product_expression():
    assert render([0.0] * 3, 100) == "[0.0, 0.0, 0.0]"


def test_equal_but_distinct_values_do_not_collapse():
    assert render([0, False] * 3, 100) == "[0, False, 0, False, 0, False]"
    assert render([0.0, -0.0], 100) == "[0.0, -0.0]"
    assert render([{"a": 1}, {"a": 1}], 100) == "[{'a': 1}, {'a': 1}]"


def test_uniformity_check_never_runs_subclass_comparisons():
    class WeirdInt(int):
        def __eq__(self, other):
            raise RuntimeError("no comparisons allowed")

        __ne__ = __eq__
        __hash__ = int.__hash__

    result = render([WeirdInt(1), WeirdInt(2)], 5, inference="off")

    assert len(result) <= 5

    shared = WeirdInt(3)

    assert render([shared] * 40, 30, inference="off") == "[3] * 40"


def test_oversized_elements_are_rejected_before_the_uniformity_scan():
    values = [("x" * 100_000) for _ in range(50)]

    result = render(values, 40)

    assert "*" not in result
    assert len(result) <= 40


def test_uniformity_proof_is_bounded_by_the_work_allowance():
    value = [0] * 10_000

    # A small budget must not fund a 10k-element uniformity scan.
    assert render(value, 40) == "[0, 0, 0, 0, 0, 0, 0, 0, ...9992 more]"
    assert render(value, 3_000) == "[0] * 10000"


def test_self_referencing_counter_uses_circular_marker():
    value = collections.Counter()
    value["self"] = value

    assert render(value, 20_000, inference="off") == "Counter({'self': <...>})"


def test_counter_with_unsortable_values_matches_native_insertion_order():
    value = collections.Counter()
    value["a"] = 1
    value["b"] = "text"

    assert render(value, 100, inference="off") == repr(value)


def test_shared_child_is_not_mistaken_for_cycle():
    shared = [1, 2, 3]
    value = [shared, shared]

    assert render(value, 100, inference="off") == repr(value)


def test_shorter_complete_child_replaces_larger_type_stub():
    value = {"empty": [], "payload": "x" * 100}

    result = render(value, 45, inference="off")

    assert "'empty': []" in result
    assert len(result) <= 45
