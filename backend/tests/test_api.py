import importlib
import json
import os
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def make_client(tmp_path):
    os.environ["FRAGMENTED_SUNSHINE_DATA_DIR"] = str(tmp_path)
    import app.main

    module = importlib.reload(app.main)
    return module, TestClient(module.app)


def test_objects_are_seeded(tmp_path):
    _, test_client = make_client(tmp_path)
    with test_client as client:
        response = client.get("/api/objects")
        assert response.status_code == 200
        assert {item["object_id"] for item in response.json()} == {
            "plush_01",
            "card_01",
            "perfume_01",
            "guitar_01",
            "boat_01",
            "r2d2_01",
            "banknote_01",
        }
        assert (
            next(item["class_name"] for item in response.json() if item["object_id"] == "boat_01")
            == "sailboat"
        )

        created = client.post(
            "/api/objects",
            json={
                "object_id": "cup_01",
                "class_name": "ceramic_cup",
                "display_name": "Ceramic cup",
            },
        )
        assert created.status_code == 201
        assert created.json()["location_x"] is None
        assert created.json()["location_y"] is None

        updated = client.patch(
            "/api/objects/perfume_01/location",
            json={"location_x": 0.4, "location_y": 0.6, "touch_radius": 0.09},
        )
        assert updated.status_code == 200
        assert updated.json()["location_x"] == 0.4
        assert updated.json()["touch_radius"] == 0.09

        reset = client.delete("/api/objects/perfume_01/location")
        assert reset.status_code == 200
        assert reset.json()["location_x"] is None
        assert reset.json()["location_y"] is None
        assert reset.json()["touch_radius"] == 0.08


def test_recording_process_and_playback_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-ci-key")
    fake_generate = Mock(
        return_value=SimpleNamespace(
            text=json.dumps(
                {
                    "segments": [
                        {"start": 0.0, "end": 6.0, "text": "A remembered beginning"},
                        {"start": 6.0, "end": 16.0, "text": "A remembered ending"},
                    ]
                }
            )
        )
    )
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=fake_generate))
    monkeypatch.setattr("app.services.genai.Client", lambda **_: fake_client)
    monkeypatch.setattr("app.services.shutil.which", lambda _: None)
    module, test_client = make_client(tmp_path)
    module.processor.gemini_api_key = "fake-ci-key"
    monkeypatch.setattr(
        module.processor,
        "_transcribe",
        lambda _: {
            "language": "en",
            "segments": [
                {"start": 0.0, "end": 6.0, "text": "A remembered beginning"},
                {"start": 6.0, "end": 16.0, "text": "A remembered ending"},
            ],
        },
    )

    with test_client as client:
        upload = client.post(
            "/api/recordings",
            data={
                "object_id": "perfume_01",
                "started_at": "2026-06-06T14:00:00+08:00",
                "ended_at": "2026-06-06T14:00:16+08:00",
            },
            files={"video_file": ("reflection.webm", b"demo", "video/webm")},
        )
        assert upload.status_code == 201
        recording_id = upload.json()["recording_id"]

        processed = client.post(f"/api/recordings/{recording_id}/process")
        assert processed.status_code == 200
        assert processed.json()["processing_status"] == "ready"
        assert [segment["transcript_text"] for segment in processed.json()["segments"]] == [
            "A remembered beginning",
            "A remembered ending",
        ]
        assert fake_generate.call_count == 1

        transcript = client.get(f"/api/recordings/{recording_id}/transcript")
        assert transcript.status_code == 200
        assert transcript.json()["language"] == "en"
        assert len(transcript.json()["segments"]) == 2

        playback = client.get("/api/objects/perfume_01/playback")
        assert playback.status_code == 200
        assert playback.json()["replay_count"] == 1
        assert len(playback.json()["timeline"]) == 2

        event = client.post(
            "/api/objects/perfume_01/playback-events",
            json={
                "recording_id": recording_id,
                "timeline": playback.json()["timeline"],
                "played_at": "2026-06-06T14:01:00+08:00",
            },
        )
        assert event.status_code == 201

        next_playback = client.get("/api/objects/perfume_01/playback")
        assert next_playback.status_code == 200
        assert next_playback.json()["replay_count"] == 2
        assert next_playback.json()["timeline"] != playback.json()["timeline"]


def test_vision_event_is_forwarded_over_websocket(tmp_path):
    _, test_client = make_client(tmp_path)
    with test_client as client, client.websocket_connect("/api/vision/events") as websocket:
        response = client.post(
            "/api/vision/events",
            json={
                "event_type": "object_activated",
                "timestamp": 1.0,
                "object_id": "perfume_01",
                "handedness": "left",
                "hands": [],
                "objects": [],
            },
        )
        assert response.status_code == 202
        assert websocket.receive_json()["event_type"] == "object_activated"


def test_recording_camera_frame_is_forwarded_over_websocket(tmp_path):
    _, test_client = make_client(tmp_path)
    with test_client as client, client.websocket_connect("/api/vision/events") as websocket:
        response = client.post(
            "/api/vision/events",
            json={
                "event_type": "recording_frame",
                "timestamp": 1.0,
                "frame_image": "data:image/jpeg;base64,dGVzdA==",
            },
        )
        assert response.status_code == 202
        event = websocket.receive_json()
        assert event["event_type"] == "recording_frame"
        assert event["frame_image"] == "data:image/jpeg;base64,dGVzdA=="
