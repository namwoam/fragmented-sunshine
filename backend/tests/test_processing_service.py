import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.database import Database
from app.services import ProcessingService

pytestmark = pytest.mark.unit


def test_gemini_segmentation_uses_structured_response_without_network(tmp_path, monkeypatch):
    generated = Mock(
        return_value=SimpleNamespace(
            text=json.dumps(
                {
                    "segments": [
                        {"start": 0.0, "end": 2.0, "text": "First fragment"},
                        {"start": 2.0, "end": 4.0, "text": "Second fragment"},
                    ]
                }
            )
        )
    )
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=generated))
    monkeypatch.setattr("app.services.genai.Client", lambda **_: fake_client)
    service = ProcessingService(
        Database(tmp_path / "test.db"),
        tmp_path,
        gemini_api_key="fake-ci-key",
        gemini_model="fake-gemini-model",
    )

    result = service._segment_transcript(
        [{"start": 0.0, "end": 4.0, "text": "First fragment Second fragment"}]
    )

    assert [segment["text"] for segment in result] == ["First fragment", "Second fragment"]
    assert generated.call_count == 1
    assert generated.call_args.kwargs["model"] == "fake-gemini-model"
    assert generated.call_args.kwargs["config"]["response_mime_type"] == "application/json"


def test_gemini_failure_falls_back_to_original_segments(tmp_path, monkeypatch):
    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=Mock(side_effect=RuntimeError("offline")))
    )
    monkeypatch.setattr("app.services.genai.Client", lambda **_: fake_client)
    service = ProcessingService(
        Database(tmp_path / "test.db"),
        tmp_path,
        gemini_api_key="fake-ci-key",
    )
    original = [{"start": 0.0, "end": 2.0, "text": "Unchanged"}]

    assert service._segment_transcript(original) == original


def test_asr_zero_length_timestamp_uses_next_segment_boundary(tmp_path):
    service = ProcessingService(Database(tmp_path / "test.db"), tmp_path)

    result = service._normalize_asr_segments(
        [
            {"start": 1.0, "end": 1.0, "text": "First"},
            {"start": 2.5, "end": 4.0, "text": "Second"},
        ],
        5.0,
    )

    assert result[0]["end"] == 2.5


def test_asr_minute_relative_timestamps_are_unwrapped(tmp_path):
    service = ProcessingService(Database(tmp_path / "test.db"), tmp_path)

    result = service._normalize_asr_segments(
        [
            {"start": 57.0, "end": 59.0, "text": "Before"},
            {"start": 1.0, "end": 4.0, "text": "After"},
        ],
        120.0,
    )

    assert result[1]["start"] == 61.0
    assert result[1]["end"] == 64.0


def test_transcription_extracts_audio_and_persists_timestamped_result(tmp_path, monkeypatch):
    media = tmp_path / "source.mp4"
    media.write_bytes(b"media")
    recording_dir = tmp_path / "objects" / "object_1" / "recordings" / "recording_1"
    recording_dir.mkdir(parents=True)
    uploaded = SimpleNamespace(name="files/audio", state=None)
    files = SimpleNamespace(
        upload=Mock(return_value=uploaded),
        delete=Mock(),
    )
    generated = Mock(
        return_value=SimpleNamespace(
            text=json.dumps(
                {
                    "language": "zh-TW",
                    "segments": [{"start": 0.0, "end": 2.5, "text": "測試語音"}],
                },
                ensure_ascii=False,
            )
        )
    )
    client = SimpleNamespace(files=files, models=SimpleNamespace(generate_content=generated))
    monkeypatch.setattr("app.services.genai.Client", lambda **_: client)
    monkeypatch.setattr("app.services.shutil.which", lambda _: "/usr/bin/ffmpeg")
    service = ProcessingService(
        Database(tmp_path / "test.db"),
        tmp_path,
        gemini_api_key="fake-ci-key",
        asr_model="fake-asr-model",
    )

    def fake_ffmpeg(command, _message):
        Path(command[-1]).write_bytes(b"wav")

    monkeypatch.setattr(service, "_run_ffmpeg", fake_ffmpeg)
    result = service._load_or_create_transcript(
        {
            "recording_id": "recording_1",
            "object_id": "object_1",
            "audio_path": None,
            "video_path": str(media),
            "duration_seconds": 3.0,
        }
    )

    assert result["language"] == "zh-TW"
    assert result["segments"][0]["text"] == "測試語音"
    assert generated.call_args.kwargs["model"] == "fake-asr-model"
    assert files.upload.call_count == 1
    assert files.delete.call_count == 1
    assert (recording_dir / "transcript.json").exists()


def test_timeline_render_requires_a_complete_permutation(tmp_path, monkeypatch):
    database = Database(tmp_path / "test.db")
    database.initialize()
    media = tmp_path / "source.mp4"
    media.write_bytes(b"media")
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO objects (object_id, class_name, display_name, created_at) "
            "VALUES ('object_1', 'test', 'Test', 'now')"
        )
        connection.execute(
            "INSERT INTO recordings VALUES "
            "('recording_1', 'object_1', ?, NULL, 4, 'now', 'now', 'now', 'ready', NULL)",
            (str(media),),
        )
        connection.executemany(
            "INSERT INTO segments VALUES (?, 'recording_1', ?, ?, ?, NULL, ?)",
            [
                ("segment_1", 0.0, 2.0, "First", 1),
                ("segment_2", 2.0, 4.0, "Second", 2),
            ],
        )
    monkeypatch.setattr("app.services.shutil.which", lambda _: "/usr/bin/ffmpeg")
    service = ProcessingService(database, tmp_path)

    def fake_ffmpeg(command, _message):
        Path(command[-1]).touch()

    monkeypatch.setattr(service, "_run_ffmpeg", fake_ffmpeg)
    render = service.render_timeline("recording_1", ["segment_2", "segment_1"])

    assert render["timeline"] == ["segment_2", "segment_1"]
    assert render["duration_seconds"] == 4.0
    with pytest.raises(ValueError, match="every segment exactly once"):
        service.render_timeline("recording_1", ["segment_1", "segment_1"])
