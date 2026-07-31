"""Bounded runtime inference for aggregate type and record-shape hints."""

import collections
import itertools

from .context import InferencePolicy, InspectionBudget
from .schema import (
    FieldSchema,
    MappingSchema,
    RecordSchema,
    ScalarSchema,
    Schema,
    SequenceSchema,
    UnionSchema,
)

EXACT_ELEMENT_LIMIT = 256
SAMPLE_SIZE = 32
MAX_SCHEMA_DEPTH = 3
MAX_RECORD_FIELDS = 32
MAX_RECORD_KEY_CHARS = 1_024
MAX_TYPE_NAME_CHARS = 128


def infer_schema(
    obj: object,
    policy: InferencePolicy,
    inspection: InspectionBudget,
    *,
    record_mapping: bool = True,
) -> Schema | None:
    """Infer a schema under the selected policy and inspection budget."""
    if policy == "off":
        return None
    return _infer(obj, policy, inspection, 0, set(), record_mapping=record_mapping)


def _infer(
    obj: object,
    policy: InferencePolicy,
    inspection: InspectionBudget,
    depth: int,
    active: set[int],
    *,
    record_mapping: bool = False,
) -> Schema | None:
    if depth > MAX_SCHEMA_DEPTH or not inspection.consume():
        return None

    scalar = _scalar_schema(obj)
    if scalar is not None:
        return scalar

    if not isinstance(
        obj,
        (list, tuple, set, frozenset, dict, collections.deque),
    ):
        return ScalarSchema(_type_name(obj))

    obj_id = id(obj)
    if obj_id in active:
        return None
    active.add(obj_id)
    try:
        if isinstance(obj, dict):
            if record_mapping and _is_record_mapping(obj):
                return _infer_record(obj, policy, inspection, depth, active)
            return _infer_mapping(obj, policy, inspection, depth, active)

        kind = _type_name(obj)
        values, complete = _sequence_values(obj, policy)
        if policy == "exact" and not complete:
            return SequenceSchema(kind, None)
        schemas = [
            _infer(
                value,
                policy,
                inspection,
                depth + 1,
                active,
                record_mapping=isinstance(value, dict),
            )
            for value in values
        ]
        if policy == "exact" and any(schema is None for schema in schemas):
            return SequenceSchema(kind, None)
        missing_schema = any(schema is None for schema in schemas)
        item = _merge_schemas([schema for schema in schemas if schema is not None])
        if missing_schema and isinstance(item, RecordSchema):
            item = RecordSchema(item.fields, complete=False)
        return SequenceSchema(kind, item)
    finally:
        active.discard(obj_id)


def _scalar_schema(obj: object) -> Schema | None:
    if obj is None:
        return ScalarSchema("None")
    if isinstance(obj, bool):
        return ScalarSchema("bool")
    if isinstance(obj, int):
        return ScalarSchema("int")
    if isinstance(obj, float):
        return ScalarSchema("float")
    if isinstance(obj, str):
        return ScalarSchema("str")
    if isinstance(obj, bytes):
        return ScalarSchema("bytes")
    return None


def _sequence_values(
    obj: list | tuple | set | frozenset | collections.deque,
    policy: InferencePolicy,
) -> tuple[list[object], bool]:
    length = len(obj)
    if length <= EXACT_ELEMENT_LIMIT:
        return list(obj), True
    if policy == "exact":
        return [], False

    if isinstance(obj, (list, tuple)):
        indices = set(range(min(8, length)))
        indices.update(range(max(0, length - 8), length))
        for step in range(1, 17):
            indices.add((step * (length - 1)) // 17)
        return [obj[index] for index in sorted(indices)[:SAMPLE_SIZE]], False

    if isinstance(obj, collections.deque):
        head = list(itertools.islice(obj, SAMPLE_SIZE // 2))
        tail = list(itertools.islice(reversed(obj), SAMPLE_SIZE // 2))
        tail.reverse()
        return (head + tail)[:SAMPLE_SIZE], False

    return list(itertools.islice(obj, SAMPLE_SIZE)), False


def _infer_mapping(
    obj: dict,
    policy: InferencePolicy,
    inspection: InspectionBudget,
    depth: int,
    active: set[int],
) -> Schema:
    items, complete = _mapping_items(obj, policy)
    if policy == "exact" and not complete:
        return MappingSchema(None, None)

    key_schemas = []
    value_schemas = []
    for key, value in items:
        key_schema = _infer(key, policy, inspection, depth + 1, active)
        value_schema = _infer(
            value,
            policy,
            inspection,
            depth + 1,
            active,
            record_mapping=isinstance(value, dict),
        )
        if policy == "exact" and (key_schema is None or value_schema is None):
            return MappingSchema(None, None)
        if key_schema is not None:
            key_schemas.append(key_schema)
        if value_schema is not None:
            value_schemas.append(value_schema)
    return MappingSchema(
        _merge_schemas(key_schemas),
        _merge_schemas(value_schemas),
    )


def _infer_record(
    obj: dict,
    policy: InferencePolicy,
    inspection: InspectionBudget,
    depth: int,
    active: set[int],
) -> RecordSchema | None:
    fields = []
    complete = True
    for key, value in itertools.islice(obj.items(), MAX_RECORD_FIELDS):
        value_schema = _infer(
            value,
            policy,
            inspection,
            depth + 1,
            active,
            record_mapping=isinstance(value, dict),
        )
        if policy == "exact" and value_schema is None:
            return None
        if value_schema is None:
            complete = False
            continue
        if not _schema_is_complete(value_schema):
            complete = False
        fields.append(FieldSchema(key, value_schema))
    return RecordSchema(tuple(fields), complete=complete)


def _mapping_items(
    obj: dict, policy: InferencePolicy
) -> tuple[list[tuple[object, object]], bool]:
    if len(obj) <= EXACT_ELEMENT_LIMIT:
        return list(obj.items()), True
    if policy == "exact":
        return [], False
    return list(itertools.islice(obj.items(), SAMPLE_SIZE)), False


def _is_record_mapping(obj: dict) -> bool:
    return (
        len(obj) <= MAX_RECORD_FIELDS
        and all(isinstance(key, str) for key in obj)
        and sum(len(key) for key in obj) <= MAX_RECORD_KEY_CHARS
    )


def _type_name(obj: object) -> str:
    name = type(obj).__name__
    return name if len(name) <= MAX_TYPE_NAME_CHARS else "object"


def _merge_schemas(schemas: list[Schema]) -> Schema | None:
    if not schemas:
        return None

    members: list[Schema] = []
    for schema in schemas:
        candidates = schema.members if isinstance(schema, UnionSchema) else (schema,)
        for candidate in candidates:
            if candidate not in members:
                members.append(candidate)

    if all(isinstance(member, RecordSchema) for member in members):
        return _merge_records(
            [member for member in members if isinstance(member, RecordSchema)]
        )
    if len(members) == 1:
        return members[0]
    members.sort(
        key=lambda member: (
            isinstance(member, ScalarSchema) and member.name == "None",
            member.format(),
        )
    )
    return UnionSchema(tuple(members))


def _merge_records(records: list[RecordSchema]) -> RecordSchema:
    keys: list[object] = []
    for record in records:
        for field in record.fields:
            if field.key not in keys:
                keys.append(field.key)

    merged = []
    for key in keys[:MAX_RECORD_FIELDS]:
        matching = [
            field for record in records for field in record.fields if field.key == key
        ]
        value = _merge_schemas([field.value for field in matching])
        if value is not None:
            merged.append(
                FieldSchema(
                    key,
                    value,
                    optional=len(matching) < len(records),
                )
            )
    return RecordSchema(
        tuple(merged),
        complete=all(record.complete for record in records),
    )


def _schema_is_complete(schema: Schema) -> bool:
    """Whether inference produced every nested record field it inspected."""
    if isinstance(schema, RecordSchema):
        return schema.complete and all(
            _schema_is_complete(field.value) for field in schema.fields
        )
    if isinstance(schema, SequenceSchema):
        return schema.item is None or _schema_is_complete(schema.item)
    if isinstance(schema, MappingSchema):
        return all(
            item is None or _schema_is_complete(item)
            for item in (schema.key, schema.value)
        )
    if isinstance(schema, UnionSchema):
        return all(_schema_is_complete(member) for member in schema.members)
    return True
