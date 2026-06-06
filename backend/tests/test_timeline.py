import pytest

from app.timeline import reorder_segments

pytestmark = pytest.mark.unit


def test_first_replay_keeps_original_order():
    segments = ["one", "two", "three", "four"]
    assert reorder_segments(segments, 1) == segments


def test_early_replay_swaps_one_adjacent_pair():
    segments = ["one", "two", "three", "four"]
    changed = reorder_segments(segments, 2)
    differing = [index for index, value in enumerate(changed) if value != segments[index]]
    assert len(differing) == 2
    assert differing[1] - differing[0] == 1
    assert sorted(changed) == sorted(segments)


def test_later_replay_is_deterministic_and_keeps_every_segment():
    segments = ["one", "two", "three", "four"]
    assert reorder_segments(segments, 8) == reorder_segments(segments, 8)
    assert sorted(reorder_segments(segments, 8)) == sorted(segments)
