from unittest.mock import Mock

import pytest

camera_client = pytest.importorskip("vision.camera_client")

pytestmark = pytest.mark.unit


def test_infer_posts_frame_and_object_catalog_to_remote_service():
    response = Mock()
    response.json.return_value = {"timestamp": 42.5, "hands": [], "objects": []}
    client = Mock()
    client.post.return_value = response
    registrations = [{"object_id": "sailboat_01", "class_name": "sailboat"}]

    result = camera_client.infer(
        client,
        "https://vision.example.com/",
        "shared-secret",
        4.0,
        42.5,
        b"jpeg-data",
        registrations,
    )

    assert result.timestamp == 42.5
    response.raise_for_status.assert_called_once_with()
    client.post.assert_called_once_with(
        "https://vision.example.com/infer",
        headers={"Authorization": "Bearer shared-secret"},
        data={
            "timestamp": "42.5",
            "objects": '[{"object_id": "sailboat_01", "class_name": "sailboat"}]',
        },
        files={"frame": ("tray.jpg", b"jpeg-data", "image/jpeg")},
        timeout=4.0,
    )


def test_registered_objects_are_cached_between_frames():
    response = Mock()
    response.json.return_value = [
        {
            "object_id": "r2d2_01",
            "class_name": "R2-D2 robot",
            "display_name": "R2-D2",
        }
    ]
    client = Mock()
    client.get.return_value = response
    objects = camera_client.RegisteredObjects("http://localhost:8000/")

    first = objects.get(client, 10.0)
    second = objects.get(client, 11.0)

    assert first == [{"object_id": "r2d2_01", "class_name": "R2-D2 robot"}]
    assert second == first
    client.get.assert_called_once_with("http://localhost:8000/api/objects", timeout=1)
