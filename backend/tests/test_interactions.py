import pytest

from vision.interactions import InteractionStateManager

pytestmark = pytest.mark.unit

OBJECT = {
    "object_id": "perfume_01",
    "bbox": {"x1": 0.4, "y1": 0.4, "x2": 0.6, "y2": 0.7},
}
LEFT_HAND = {
    "handedness": "left",
    "bbox": {"x1": 0.42, "y1": 0.42, "x2": 0.62, "y2": 0.75},
}


def test_stable_left_hand_lift_and_return_emit_events():
    manager = InteractionStateManager(debounce_seconds=0.4)
    assert manager.update(0.0, [], [OBJECT]) == []
    assert manager.update(0.5, [], [OBJECT]) == []
    assert manager.update(0.6, [LEFT_HAND], [OBJECT]) == []
    lifted = manager.update(1.1, [LEFT_HAND], [OBJECT])
    assert lifted[0]["event_type"] == "object_lifted"
    assert lifted[0]["handedness"] == "left"
    assert manager.update(1.2, [], [OBJECT]) == []
    returned = manager.update(1.7, [], [OBJECT])
    assert returned[0]["event_type"] == "object_returned"


def test_unstable_overlap_is_debounced():
    manager = InteractionStateManager(debounce_seconds=0.4)
    manager.update(0.0, [], [OBJECT])
    manager.update(0.5, [], [OBJECT])
    manager.update(0.6, [LEFT_HAND], [OBJECT])
    manager.update(0.7, [], [OBJECT])
    assert manager.update(1.2, [], [OBJECT]) == []
