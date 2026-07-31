"""Inference-policy contracts for the private rendering engine."""

from reprobate._engine import render
from reprobate._engine.context import InspectionBudget
from reprobate._engine.inference import infer_schema


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


def test_record_sequence_summary_includes_sample_values_when_affordable():
    value = [{"name": f"user_{index}", "score": index * 10} for index in range(50)]

    result = render(value, 90)

    assert result.startswith("<list[{'name': str, 'score': int}](50): ")
    assert "{'name': 'user_0', 'score': 0}" in result
    assert result.endswith(", ...>")
    assert len(result) <= 90


def test_record_sequence_summary_spends_a_near_full_budget_on_samples():
    value = [{"name": f"user_{index}", "score": index * 10} for index in range(50)]
    budget = len(repr(value)) - 1

    result = render(value, budget)

    assert "'score': 10" in result
    assert len(result) > budget * 0.9


def test_record_sequence_summary_degrades_to_bare_schema():
    value = [{"name": f"user_{index}", "score": index * 10} for index in range(50)]

    assert render(value, 60) == "<list[{'name': str, 'score': int}](50)>"


def test_standalone_fixed_record_inference_preserves_literal_keys():
    value = {
        "users": ["alice" * 30] * 200,
        "cursor": "abc" * 100,
    }

    result = render(value, 42)

    assert result == "<{'users': list[str], 'cursor': str}>"


def test_nested_fixed_record_inference_preserves_field_associations():
    value = {
        "status": "ok",
        "result": {
            "users": ["alice" * 30] * 200,
            "cursor": "abc" * 100,
        },
    }

    result = render(value, 72, policy="even")

    assert "'result': <{'users': list[str], 'cursor': str}>" in result


def test_real_mapping_value_takes_priority_over_record_schema():
    value = {"parse": 1.25, "run": 2.5, "total": 3.75}

    assert render(value, 100) == repr(value)


def test_open_mapping_inference_uses_key_and_value_types():
    value = {f"long-key-{index}": "x" * 100 for index in range(300)}

    assert render(value, 25) == "<dict[str, str](300)>"
    assert render(value, 25, inference="exact") == "<dict(300)>"


def test_exact_inference_degrades_when_nested_inspection_budget_is_exhausted():
    value = [{f"field-{field}": field for field in range(32)} for _ in range(256)]

    result = render(value, 40, inference="exact")

    assert "list[" not in result
    assert len(result) <= 40


def test_complete_empty_collection_still_prefers_its_real_value():
    assert render([], 20) == "[]"


def test_best_effort_sequence_inference_reads_at_most_the_sample_limit():
    class TrackingList(list):
        def __init__(self):
            super().__init__(["value"] * 10_000)
            self.reads = 0

        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)

    value = TrackingList()

    schema = infer_schema(value, "best_effort", InspectionBudget())

    assert schema is not None
    assert value.reads <= 32


def test_exact_sequence_inference_rejects_large_input_without_indexing_it():
    class TrackingList(list):
        def __init__(self):
            super().__init__(["value"] * 10_000)
            self.reads = 0

        def __getitem__(self, index):
            self.reads += 1
            return super().__getitem__(index)

    value = TrackingList()

    schema = infer_schema(value, "exact", InspectionBudget())

    assert schema is not None
    assert schema.format() == "TrackingList"
    assert value.reads == 0


def test_pathological_record_keys_degrade_to_a_bounded_open_mapping_schema():
    value = [{"field" * 10_000: 1}]

    schema = infer_schema(value, "best_effort", InspectionBudget())

    assert schema is not None
    assert schema.format() == "list[dict[str, int]]"


def test_pathological_runtime_type_names_degrade_to_object():
    huge_type = type("T" * 10_000, (), {})
    value = [huge_type()]

    schema = infer_schema(value, "best_effort", InspectionBudget())

    assert schema is not None
    assert schema.format() == "list[object]"
