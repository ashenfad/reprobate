"""Render-session state for the replacement engine."""

from dataclasses import dataclass, field
from typing import Literal

Policy = Literal["greedy", "even"]
InferencePolicy = Literal["off", "exact", "best_effort"]


@dataclass
class RenderContext:
    """State propagated through one replacement-engine render call."""

    policy: Policy
    inference: InferencePolicy
    seen: set[int] = field(default_factory=set)
