"""Render-session state for the rendering engine."""

from dataclasses import dataclass, field
from typing import Literal

Policy = Literal["greedy", "even"]
InferencePolicy = Literal["off", "exact", "best_effort"]
MAX_INSPECTION_NODES = 1_024
MIN_RENDER_WORK_NODES = 1_024
RENDER_WORK_NODES_PER_CHAR = 4


@dataclass
class InspectionBudget:
    remaining: int = MAX_INSPECTION_NODES

    def consume(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass
class RenderContext:
    """State propagated through one engine render call."""

    policy: Policy
    inference: InferencePolicy
    seen: set[int] = field(default_factory=set)
    inspection: InspectionBudget = field(default_factory=InspectionBudget)
    work: InspectionBudget = field(default_factory=InspectionBudget)
    schema_cache: dict[tuple[int, bool], object | None] = field(default_factory=dict)


def render_work_budget(budget: int) -> InspectionBudget:
    """Create a work allowance that is bounded and scales with possible output."""
    return InspectionBudget(
        max(MIN_RENDER_WORK_NODES, budget * RENDER_WORK_NODES_PER_CHAR)
    )
