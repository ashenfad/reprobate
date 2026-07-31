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


def test_shared_child_is_not_mistaken_for_cycle():
    shared = [1, 2, 3]
    value = [shared, shared]

    assert render(value, 100, inference="off") == repr(value)


def test_shorter_complete_child_replaces_larger_type_stub():
    value = {"empty": [], "payload": "x" * 100}

    result = render(value, 45, inference="off")

    assert "'empty': []" in result
    assert len(result) <= 45
