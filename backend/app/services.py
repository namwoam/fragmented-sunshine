import json
import shutil
import subprocess
from pathlib import Path

from google import genai
from pydantic import BaseModel

from .database import Database, now_iso


class TranscriptUnit(BaseModel):
    start: float
    end: float
    text: str


class SegmentedTranscript(BaseModel):
    segments: list[TranscriptUnit]


class ProcessingService:
    def __init__(
        self,
        database: Database,
        data_dir: Path,
        gemini_api_key: str | None = None,
        gemini_model: str = "gemini-2.5-flash",
    ):
        self.database = database
        self.data_dir = data_dir
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model

    @property
    def ffmpeg_available(self) -> bool:
        return shutil.which("ffmpeg") is not None

    def process(self, recording_id: str) -> list[dict]:
        with self.database.connection() as connection:
            recording = connection.execute(
                "SELECT * FROM recordings WHERE recording_id = ?", (recording_id,)
            ).fetchone()
            if not recording:
                raise LookupError("Recording not found")
            connection.execute(
                "UPDATE recordings SET processing_status = 'processing', error_message = NULL "
                "WHERE recording_id = ?",
                (recording_id,),
            )

        try:
            transcript = self._load_or_create_transcript(dict(recording))
            segments = self._segment_transcript(transcript)
            self._store_segments(recording_id, dict(recording), segments)
            with self.database.connection() as connection:
                connection.execute(
                    "UPDATE recordings SET processing_status = 'ready' WHERE recording_id = ?",
                    (recording_id,),
                )
            return segments
        except Exception as exc:
            with self.database.connection() as connection:
                connection.execute(
                    "UPDATE recordings SET processing_status = 'failed', error_message = ? "
                    "WHERE recording_id = ?",
                    (str(exc), recording_id),
                )
            raise

    def _load_or_create_transcript(self, recording: dict) -> list[dict]:
        recording_dir = (
            self.data_dir
            / "objects"
            / recording["object_id"]
            / "recordings"
            / recording["recording_id"]
        )
        transcript_path = recording_dir / "transcript.json"
        if transcript_path.exists():
            payload = json.loads(transcript_path.read_text(encoding="utf-8"))
            return payload.get("segments", [])

        duration = max(float(recording["duration_seconds"]), 1.0)
        chunk_count = max(1, min(4, round(duration / 8)))
        chunk_duration = duration / chunk_count
        segments = [
            {
                "start": round(index * chunk_duration, 3),
                "end": round(min((index + 1) * chunk_duration, duration), 3),
                "text": f"Memory fragment {index + 1}",
            }
            for index in range(chunk_count)
        ]
        transcript_path.write_text(
            json.dumps({"language": "und", "segments": segments}, indent=2), encoding="utf-8"
        )
        return segments

    def _segment_transcript(self, segments: list[dict]) -> list[dict]:
        if not self.gemini_api_key or not segments:
            return segments

        client = genai.Client(api_key=self.gemini_api_key)
        prompt = (
            "Segment the timestamped transcript into short, semantically meaningful, "
            "reorderable spoken units. Preserve every original word and timestamp range. "
            "Do not summarize, rewrite, translate, or add content. Do not create gaps or "
            "overlaps. Return only data matching the supplied schema.\n\nTranscript:\n"
            + json.dumps(segments, ensure_ascii=False)
        )
        try:
            response = client.models.generate_content(
                model=self.gemini_model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": SegmentedTranscript.model_json_schema(),
                    "temperature": 0,
                },
            )
            result = SegmentedTranscript.model_validate_json(response.text)
            return [segment.model_dump() for segment in result.segments]
        except Exception:
            # Keep the installation usable during network or model outages.
            return segments

    def _store_segments(self, recording_id: str, recording: dict, segments: list[dict]) -> None:
        recording_dir = (
            self.data_dir / "objects" / recording["object_id"] / "recordings" / recording_id
        )
        segment_dir = recording_dir / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        stored = []
        with self.database.connection() as connection:
            connection.execute("DELETE FROM segments WHERE recording_id = ?", (recording_id,))
            for index, segment in enumerate(segments, start=1):
                segment_id = f"{recording_id}_seg_{index:02d}"
                segment_path = None
                if self.ffmpeg_available and recording["video_path"]:
                    output = segment_dir / f"{segment_id}.webm"
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-i",
                            recording["video_path"],
                            "-ss",
                            str(segment["start"]),
                            "-to",
                            str(segment["end"]),
                            "-c:v",
                            "libvpx-vp9",
                            "-c:a",
                            "libopus",
                            str(output),
                        ],
                        check=True,
                        capture_output=True,
                    )
                    segment_path = str(output)
                connection.execute(
                    "INSERT INTO segments VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        segment_id,
                        recording_id,
                        segment["start"],
                        segment["end"],
                        segment["text"],
                        segment_path,
                        index,
                    ),
                )
                stored.append({"segment_id": segment_id, **segment})
        (recording_dir / "segments.json").write_text(
            json.dumps({"segments": stored}, indent=2), encoding="utf-8"
        )
        (recording_dir / "processed_at.txt").write_text(now_iso(), encoding="utf-8")
