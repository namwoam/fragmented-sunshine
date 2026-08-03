import pytest

from app.timeline import reorder_segments

pytestmark = pytest.mark.unit


def test_playback_uses_random_shuffle(monkeypatch):
    segments = ["one", "two", "three", "four"]
    monkeypatch.setattr("app.timeline.random.shuffle", lambda items: items.reverse())

    assert reorder_segments(segments) == ["four", "three", "two", "one"]
    assert segments == ["one", "two", "three", "four"]


def test_shuffle_keeps_every_segment_exactly_once():
    segments = ["one", "two", "three", "four"]

    changed = reorder_segments(segments)

    assert changed != segments
    assert sorted(changed) == sorted(segments)


def test_unchanged_random_result_rotates_to_avoid_original_order(monkeypatch):
    segments = ["one", "two", "three", "four"]
    monkeypatch.setattr("app.timeline.random.shuffle", lambda _: None)

    assert reorder_segments(segments) == ["two", "three", "four", "one"]


def test_single_segment_remains_unchanged():
    assert reorder_segments(["one"]) == ["one"]
