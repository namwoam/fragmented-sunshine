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


def test_five_second_touch_emits_one_activation():
    manager = InteractionStateManager(dwell_seconds=5.0)
    assert manager.update(0.0, [LEFT_HAND], [OBJECT]) == []
    assert manager.progress(2.0) == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "elapsed_seconds": 2.0,
            "remaining_seconds": 3.0,
            "progress": 0.4,
        }
    ]
    assert manager.update(4.99, [LEFT_HAND], [OBJECT]) == []
    activated = manager.update(5.0, [LEFT_HAND], [OBJECT])
    assert activated[0]["event_type"] == "object_activated"
    assert activated[0]["handedness"] == "left"
    assert manager.progress(5.0) == []
    assert manager.update(6.0, [LEFT_HAND], [OBJECT]) == []


def test_leaving_location_resets_dwell_timer():
    manager = InteractionStateManager(dwell_seconds=5.0)
    manager.update(0.0, [LEFT_HAND], [OBJECT])
    manager.update(4.0, [], [OBJECT])
    manager.update(4.1, [LEFT_HAND], [OBJECT])
    assert manager.update(8.9, [LEFT_HAND], [OBJECT]) == []
    assert manager.update(9.1, [LEFT_HAND], [OBJECT])[0]["event_type"] == "object_activated"
