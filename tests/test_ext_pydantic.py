"""Tests for pydantic extension."""

import pytest

pydantic = pytest.importorskip("pydantic")

import reprobate


class TestBaseModel:
    def test_simple_model(self):
        class User(pydantic.BaseModel):
            name: str = "alice"
            age: int = 30

        r = reprobate.render(User(), 200)
        assert "User" in r
        assert "name=" in r
        assert "age=" in r

    def test_model_truncation(self):
        class BigModel(pydantic.BaseModel):
            a: str = "alpha"
            b: str = "bravo"
            c: str = "charlie"
            d: str = "delta"
            e: str = "echo"

        r = reprobate.render(BigModel(), 40)
        assert len(r) <= 40
        assert "BigModel" in r

    def test_budget_respected(self):
        class Config(pydantic.BaseModel):
            host: str = "localhost"
            port: int = 8080
            debug: bool = True

        for budget in [5, 10, 20, 50, 100, 200]:
            r = reprobate.render(Config(), budget)
            assert len(r) <= budget, (
                f"Budget {budget} exceeded: got {len(r)} chars: {r!r}"
            )
