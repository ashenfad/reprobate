"""Pure allocation helpers for bounded representation planning."""

from collections.abc import Sequence


def allocate_even(demands: Sequence[int | None], available: int) -> list[int]:
    """Max-min allocate extra characters across finite or open-ended demands.

    ``None`` represents a child that can potentially use every available character.
    Finite demands saturate and return their unused share to the common pool.
    """
    allocations = [0] * len(demands)
    active = [
        index for index, demand in enumerate(demands) if demand is None or demand > 0
    ]

    while available > 0 and active:
        share, bonus = divmod(available, len(active))
        spent = 0
        next_active: list[int] = []

        for position, index in enumerate(active):
            offered = share + (position < bonus)
            demand = demands[index]
            remaining = None if demand is None else demand - allocations[index]
            granted = offered if remaining is None else min(offered, remaining)
            allocations[index] += granted
            spent += granted

            if remaining is None or granted < remaining:
                next_active.append(index)

        if spent == 0:
            break
        available -= spent
        active = next_active

    return allocations
