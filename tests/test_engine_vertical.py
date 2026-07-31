"""Contract tests for the private replacement-engine walking skeleton."""

import pytest

from reprobate._engine import render


def test_complete_nested_value_is_preserved_when_it_fits():
    value = {
        "status": "ok",
        "users": ["alice", "bob", "a very long name"],
    }
    full = repr(value)

    assert render(value, len(full), inference="off") == full


def test_every_budget_is_respected_for_nested_value():
    value = {
        "status": "ok",
        "users": ["alice", "bob", "a very long name"],
    }
    full = repr(value)

    for budget in range(len(full) + 5):
        assert len(render(value, budget, inference="off")) <= budget


def test_compact_mapping_preserves_outer_structure_before_deep_detail():
    value = {
        "status": "ok",
        "users": ["alice" * 20, "bob" * 20],
        "cursor": "next-page",
    }

    result = render(value, 70, policy="even", inference="off")

    assert "'status': 'ok'" in result
    assert "'users':" in result
    assert "'cursor':" in result
    assert len(result) <= 70


def test_extra_child_budget_does_not_replace_stub_with_malformed_container():
    value = {
        "status": "ok",
        "users": ["alice" * 20, "bob" * 20],
        "cursor": "next-page",
    }

    result = render(value, 60, policy="even", inference="off")

    assert "'users': <list(2)>" in result
    assert result.endswith("}")


def test_string_preview_is_escaped_and_single_line():
    result = render("first line\nsecond line" * 20, 30, inference="off")

    assert "\\n" in result
    assert "\n" not in result
    assert len(result) <= 30


def test_large_string_uses_bounded_preview_path():
    result = render("x" * 1_000_000, 40, inference="off")

    assert len(result) <= 40
    assert "..." in result


def test_singleton_tuple_keeps_its_comma():
    assert render((1,), 4, inference="off") == "(1,)"


@pytest.mark.parametrize("policy", ["greedy", "even"])
def test_allocation_policies_are_accepted(policy):
    assert render([1, 2, 3], 100, policy=policy) == "[1, 2, 3]"


@pytest.mark.parametrize("inference", ["off", "exact", "best_effort"])
def test_inference_policies_are_accepted(inference):
    assert render([1, 2, 3], 100, inference=inference) == "[1, 2, 3]"


def test_invalid_arguments_are_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        render([], -1)
    with pytest.raises(ValueError, match="rendering policy"):
        render([], 10, policy="unknown")
    with pytest.raises(ValueError, match="inference policy"):
        render([], 10, inference="unknown")
