import random


def reorder_segments(segment_ids: list[str]) -> list[str]:
    """Return a fresh shuffled order while preserving every segment exactly once."""
    order = list(segment_ids)
    if len(order) < 2:
        return order

    random.shuffle(order)
    if order == segment_ids:
        order = order[1:] + order[:1]
    return order
