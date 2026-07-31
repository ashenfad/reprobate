"""Public facade contracts introduced by the replacement-engine cutover."""

import reprobate


def test_public_render_exposes_best_effort_inference_by_default():
    values = ["alice" * 30] * 1_000

    assert reprobate.render(values, 25) == "<list[str](1000)>"


def test_public_render_accepts_all_inference_policies():
    values = ["alice" * 30] * 1_000

    assert reprobate.render(values, 25, inference="exact") == "<list(1000)>"
    assert reprobate.render(values, 25, inference="off") == (
        "[<str(150)>, ...999 more]"
    )


def test_public_render_attrs_uses_replacement_engine_outside_a_render_call():
    result = reprobate.render_attrs(
        {"name": "alice", "values": list(range(100))},
        "Model",
        50,
    )

    assert result.startswith("Model(")
    assert len(result) <= 50


def test_inference_policy_type_is_exported():
    assert reprobate.InferencePolicy is not None
