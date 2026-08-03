import pytest

from vision.interactions import InteractionStateManager

pytestmark = pytest.mark.unit

OBJECT = {
    "object_id": "perfume_01",
    "bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.6},
}
LEFT_HAND = {
    "handedness": "left",
    "touch_x": 0.52,
    "touch_y": 0.48,
}
MOVED_LEFT_HAND = {**LEFT_HAND, "touch_x": 0.8, "touch_y": 0.8}
MOVED_RIGHT_HAND = {**MOVED_LEFT_HAND, "handedness": "right"}
OTHER_OBJECT = {
    "object_id": "card_01",
    "bbox": OBJECT["bbox"],
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


def test_occluded_object_remains_locked_to_hand_until_activation():
    manager = InteractionStateManager(dwell_seconds=3.0)

    assert manager.update(0.0, [LEFT_HAND], [OBJECT]) == []
    assert manager.locks() == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "status": "live",
            "object_visible": True,
        }
    ]
    assert manager.update(1.0, [LEFT_HAND], []) == []
    assert manager.locks() == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "status": "hand_locked",
            "object_visible": False,
        }
    ]
    assert manager.update(2.0, [LEFT_HAND], []) == []
    assert manager.update(3.0, [LEFT_HAND], []) == [
        {
            "event_type": "object_activated",
            "timestamp": 3.0,
            "object_id": "perfume_01",
            "handedness": "left",
        }
    ]
    assert manager.locks() == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "status": "activated",
            "object_visible": False,
        }
    ]


def test_lock_requires_initial_live_object_overlap():
    manager = InteractionStateManager(dwell_seconds=3.0)

    assert manager.update(0.0, [LEFT_HAND], []) == []
    assert manager.update(3.0, [LEFT_HAND], []) == []
    assert manager.progress(3.0) == []


def test_recent_object_location_can_establish_lock_after_detection_disappears():
    manager = InteractionStateManager(dwell_seconds=3.0, object_memory_seconds=1.5)

    assert manager.update(0.0, [], [OBJECT]) == []
    assert manager.update(1.0, [LEFT_HAND], []) == []
    assert manager.locks() == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "status": "hand_locked",
            "object_visible": False,
        }
    ]
    assert manager.update(4.0, [LEFT_HAND], []) == [
        {
            "event_type": "object_activated",
            "timestamp": 4.0,
            "object_id": "perfume_01",
            "handedness": "left",
        }
    ]


def test_expired_object_location_cannot_establish_lock():
    manager = InteractionStateManager(dwell_seconds=3.0, object_memory_seconds=1.5)

    manager.update(0.0, [], [OBJECT])
    assert manager.update(1.51, [LEFT_HAND], []) == []
    assert manager.locks() == []
    assert manager.progress(1.51) == []


def test_lock_does_not_transfer_to_another_hand_or_object():
    manager = InteractionStateManager(dwell_seconds=3.0)

    manager.update(0.0, [LEFT_HAND], [OBJECT])
    manager.update(1.0, [LEFT_HAND], [OTHER_OBJECT])
    assert manager.progress(1.0) == [
        {
            "object_id": "perfume_01",
            "handedness": "left",
            "elapsed_seconds": 1.0,
            "remaining_seconds": 2.0,
            "progress": 1 / 3,
        }
    ]

    manager.update(1.1, [MOVED_RIGHT_HAND], [])
    assert manager.progress(1.1) == []


def test_reappearing_object_outside_hand_releases_after_occluded_activation():
    manager = InteractionStateManager(dwell_seconds=3.0)

    manager.update(0.0, [LEFT_HAND], [OBJECT])
    manager.update(3.0, [LEFT_HAND], [])

    assert manager.update(4.0, [MOVED_LEFT_HAND], [OBJECT]) == [
        {
            "event_type": "object_released",
            "timestamp": 4.0,
            "object_id": "perfume_01",
            "handedness": "left",
        }
    ]
    assert manager.locks() == []
