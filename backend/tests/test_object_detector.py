from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from vision.objects import ObjectDetector

pytestmark = pytest.mark.unit


class Values:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


def test_detector_uses_registered_classes_and_normalizes_live_boxes():
    model = SimpleNamespace(set_classes=Mock(), predict=Mock())
    model.predict.return_value = [
        SimpleNamespace(
            orig_shape=(480, 640),
            boxes=SimpleNamespace(
                xyxy=Values([[64, 96, 320, 384]]),
                conf=Values([0.82]),
                cls=Values([0]),
            ),
        )
    ]
    registrations = [
        {
            "object_id": "perfume_01",
            "class_name": "perfume_bottle",
            "display_name": "Perfume bottle",
        }
    ]
    detector = ObjectDetector(model_factory=lambda _: model)

    detections = detector.detect(object(), registrations)

    model.set_classes.assert_called_once_with(["perfume bottle"])
    model.predict.assert_called_once()
    assert detections == [
        {
            "object_id": "perfume_01",
            "class_name": "perfume_bottle",
            "confidence": 0.82,
            "bbox": {"x1": 0.1, "y1": 0.2, "x2": 0.5, "y2": 0.8},
            "on_tray": True,
        }
    ]


def test_detector_keeps_only_the_best_match_for_one_registered_object():
    model = SimpleNamespace(set_classes=Mock(), predict=Mock())
    model.predict.return_value = [
        SimpleNamespace(
            orig_shape=(100, 100),
            boxes=SimpleNamespace(
                xyxy=Values([[0, 0, 10, 10], [20, 20, 80, 80]]),
                conf=Values([0.3, 0.9]),
                cls=Values([0, 0]),
            ),
        )
    ]
    registrations = [{"object_id": "card_01", "class_name": "handwritten_card"}]
    detector = ObjectDetector(model_factory=lambda _: model)

    detections = detector.detect(object(), registrations)

    assert len(detections) == 1
    assert detections[0]["confidence"] == 0.9
    assert detections[0]["bbox"] == {"x1": 0.2, "y1": 0.2, "x2": 0.8, "y2": 0.8}
