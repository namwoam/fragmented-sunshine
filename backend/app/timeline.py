import random


def reorder_segments(segment_ids: list[str], replay_count: int) -> list[str]:
    """Return a deterministic order with disruption increasing by replay count."""
    order = list(segment_ids)
    if len(order) < 2 or replay_count <= 1:
        return order

    randomizer = random.Random(f"fragmented-sunshine:{','.join(order)}:{replay_count}")
    if replay_count <= 3:
        index = randomizer.randrange(len(order) - 1)
        order[index], order[index + 1] = order[index + 1], order[index]
        return order

    if replay_count <= 6:
        indices = list(range(len(order) - 1))
        randomizer.shuffle(indices)
        for index in sorted(indices[: min(2, len(indices))]):
            order[index], order[index + 1] = order[index + 1], order[index]
        return order

    randomizer.shuffle(order)
    if order == segment_ids:
        order = order[1:] + order[:1]
    return order
