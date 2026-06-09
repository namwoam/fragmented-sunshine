import pytest

from vision.interactions import InteractionStateManager

pytestmark = pytest.mark.unit

OBJECT = {
    "object_id": "perfume_01",
    "location_x": 0.5,
    "location_y": 0.5,
    "touch_radius": 0.1,
}
LEFT_HAND = {
    "handedness": "left",
    "touch_x": 0.52,
    "touch_y": 0.48,
}


def test_three_second_touch_emits_one_activation():
    manager = InteractionStateManager(dwell_seconds=3.0)
    assert manager.update(0.0, [LEFT_HAND], [OBJECT]) == []
    assert manager.progress(1.0) == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "elapsed_seconds": 1.0,
            "remaining_seconds": 2.0,
            "progress": 1 / 3,
        }
    ]
    assert manager.update(2.99, [LEFT_HAND], [OBJECT]) == []
    activated = manager.update(3.0, [LEFT_HAND], [OBJECT])
    assert activated[0]["event_type"] == "object_activated"
    assert activated[0]["handedness"] == "left"
    assert manager.progress(3.0) == []
    assert manager.update(4.0, [LEFT_HAND], [OBJECT]) == []
    released = manager.update(4.1, [], [OBJECT])
    assert released == [
        {
            "event_type": "object_released",
            "timestamp": 4.1,
            "object_id": "perfume_01",
            "handedness": "left",
        }
    ]


def test_leaving_location_resets_dwell_timer():
    manager = InteractionStateManager(dwell_seconds=3.0)
    manager.update(0.0, [LEFT_HAND], [OBJECT])
    assert manager.update(2.0, [], [OBJECT]) == []
    manager.update(2.1, [LEFT_HAND], [OBJECT])
    assert manager.update(5.0, [LEFT_HAND], [OBJECT]) == []
    assert manager.update(5.11, [LEFT_HAND], [OBJECT])[0]["event_type"] == "object_activated"
