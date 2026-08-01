from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
remote = pytest.importorskip("vision.run")

pytestmark = pytest.mark.unit


def jpeg_frame() -> bytes:
    success, encoded = cv2.imencode(".jpg", np.zeros((8, 8, 3), dtype=np.uint8))
    assert success
    return encoded.tobytes()


def test_inference_endpoint_authenticates_and_passes_frame_and_objects():
    engine = SimpleNamespace(
        infer=Mock(
            return_value={
                "timestamp": 42.5,
                "hands": [],
                "objects": [],
            }
        )
    )
    client = TestClient(remote.create_app(engine, token="shared-secret"))

    response = client.post(
        "/infer",
        headers={"Authorization": "Bearer shared-secret"},
        data={
            "timestamp": "42.5",
            "objects": '[{"object_id":"guitar_01","class_name":"guitar"}]',
        },
        files={"frame": ("tray.jpg", jpeg_frame(), "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {"timestamp": 42.5, "hands": [], "objects": []}
    frame, timestamp, registrations = engine.infer.call_args.args
    assert frame.shape == (8, 8, 3)
    assert timestamp == 42.5
    assert registrations == [{"object_id": "guitar_01", "class_name": "guitar"}]


def test_inference_endpoint_rejects_invalid_token_before_inference():
    engine = SimpleNamespace(infer=Mock())
    client = TestClient(remote.create_app(engine, token="shared-secret"))

    response = client.post(
        "/infer",
        data={"timestamp": "1", "objects": "[]"},
        files={"frame": ("tray.jpg", jpeg_frame(), "image/jpeg")},
    )

    assert response.status_code == 401
    engine.infer.assert_not_called()


def test_inference_endpoint_rejects_invalid_object_catalog():
    engine = SimpleNamespace(infer=Mock())
    client = TestClient(remote.create_app(engine))

    response = client.post(
        "/infer",
        data={"timestamp": "1", "objects": "not-json"},
        files={"frame": ("tray.jpg", jpeg_frame(), "image/jpeg")},
    )

    assert response.status_code == 422
    engine.infer.assert_not_called()
