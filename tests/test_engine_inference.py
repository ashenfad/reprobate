"""Inference-policy contracts for the private replacement engine."""

from reprobate._engine import render


def test_inference_off_uses_untyped_collection_summary():
    value = ["x" * 100 for _ in range(200)]

    assert render(value, 20, inference="off") == "[...200 items]"


def test_exact_inference_scans_small_collection_completely():
    value = ["x" * 100 for _ in range(200)]

    assert render(value, 20, inference="exact") == "<list[str](200)>"


def test_exact_inference_does_not_sample_large_collection():
    value = ["x" * 100 for _ in range(1_000)]

    assert render(value, 20, inference="exact") == "<list(1000)>"


def test_best_effort_inference_samples_large_collection():
    value = ["x" * 100 for _ in range(1_000)]

    assert render(value, 20) == "<list[str](1000)>"


def test_best_effort_sample_includes_tail_elements():
    value = ["x" * 100 for _ in range(1_000)]
    value[-1] = None

    assert render(value, 24) == "<list[str | None](1000)>"


def test_record_inference_distinguishes_optional_and_nullable_fields():
    value = []
    for index in range(200):
        record = {"id": index}
        if index % 2:
            record["error"] = None if index % 4 == 1 else "bad"
        value.append(record)

    result = render(value, 100, inference="exact")

    assert "'id': int" in result
    assert "'error'?: str | None" in result


def test_open_mapping_inference_uses_key_and_value_types():
    value = {f"long-key-{index}": "x" * 100 for index in range(300)}

    assert render(value, 25) == "<dict[str, str](300)>"
    assert render(value, 25, inference="exact") == "<dict(300)>"


def test_exact_inference_degrades_when_nested_inspection_budget_is_exhausted():
    value = [{f"field-{field}": field for field in range(32)} for _ in range(256)]

    assert render(value, 40, inference="exact") == "<list(256)>"


def test_complete_empty_collection_still_prefers_its_real_value():
    assert render([], 20) == "[]"
