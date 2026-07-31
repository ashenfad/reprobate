"""Internal schema vocabulary for compact aggregate type hints."""

from dataclasses import dataclass


class Schema:
    """Base class for inferred schema fragments."""

    def format(self) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class ScalarSchema(Schema):
    name: str

    def format(self) -> str:
        return self.name


@dataclass(frozen=True)
class UnionSchema(Schema):
    members: tuple[Schema, ...]

    def format(self) -> str:
        return " | ".join(member.format() for member in self.members)


@dataclass(frozen=True)
class SequenceSchema(Schema):
    kind: str
    item: Schema | None

    def format(self) -> str:
        if self.item is None:
            return self.kind
        return f"{self.kind}[{self.item.format()}]"


@dataclass(frozen=True)
class MappingSchema(Schema):
    key: Schema | None
    value: Schema | None

    def format(self) -> str:
        if self.key is None or self.value is None:
            return "dict"
        return f"dict[{self.key.format()}, {self.value.format()}]"


@dataclass(frozen=True)
class FieldSchema:
    key: object
    value: Schema
    optional: bool = False


@dataclass(frozen=True)
class RecordSchema(Schema):
    fields: tuple[FieldSchema, ...]
    complete: bool = True

    def format(self) -> str:
        parts = []
        for field in self.fields:
            optional = "?" if field.optional else ""
            parts.append(f"{field.key!r}{optional}: {field.value.format()}")
        if not self.complete:
            parts.append("...")
        return "{" + ", ".join(parts) + "}"
