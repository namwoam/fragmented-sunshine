import json
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
