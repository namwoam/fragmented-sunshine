import hashlib
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from google import genai
from pydantic import BaseModel, Field

from .database import Database, now_iso


class TranscriptUnit(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1)


class TranscriptDocument(BaseModel):
    language: str = Field(min_length=2)
    segments: list[TranscriptUnit]


class SegmentedTranscript(BaseModel):
    segments: list[TranscriptUnit]


class ProcessingService:
    def __init__(
        self,
        database: Database,
        data_dir: Path,
        gemini_api_key: str | None = None,
        gemini_model: str = "gemini-3.5-flash-lite",
        asr_model: str | None = None,
    ):
        self.database = database
        self.data_dir = data_dir
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.asr_model = asr_model or gemini_model

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
            recording_data = dict(recording)
            transcript = self._load_or_create_transcript(recording_data)
            segments = self._segment_transcript(transcript["segments"])
            segments = self._validate_segments(
                segments,
                float(recording_data["duration_seconds"]),
                expected_text=transcript["segments"],
            )
            self._store_segments(recording_id, recording_data, segments)
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

    def _recording_dir(self, recording: dict) -> Path:
        return (
            self.data_dir
            / "objects"
            / recording["object_id"]
            / "recordings"
            / recording["recording_id"]
        )

    def _load_or_create_transcript(self, recording: dict) -> dict:
        recording_dir = self._recording_dir(recording)
        transcript_path = recording_dir / "transcript.json"
        if transcript_path.exists():
            payload = TranscriptDocument.model_validate_json(
                transcript_path.read_text(encoding="utf-8")
            )
            return payload.model_dump()

        transcript = self._transcribe(recording)
        transcript_path.write_text(
            json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return transcript

    def _transcribe(self, recording: dict) -> dict:
        if not self.gemini_api_key:
            raise RuntimeError("ASR requires GEMINI_API_KEY or a cached transcript.json")
        if not self.ffmpeg_available:
            raise RuntimeError("ASR requires ffmpeg to extract normalized audio")

        source = recording.get("audio_path") or recording.get("video_path")
        if not source or not Path(source).exists():
            raise RuntimeError("Recording media is missing")

        recording_dir = self._recording_dir(recording)
        audio_path = recording_dir / "audio_16khz_mono.wav"
        self._run_ffmpeg(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(audio_path),
            ],
            "Audio extraction failed",
        )

        client = genai.Client(api_key=self.gemini_api_key)
        uploaded = client.files.upload(
            file=audio_path,
            config={"mime_type": "audio/wav", "display_name": recording["recording_id"]},
        )
        try:
            uploaded = self._wait_for_uploaded_file(client, uploaded)
            prompt = (
                "Transcribe this recording verbatim. Preserve Traditional Chinese characters, "
                "Taiwanese Mandarin wording, English code-switching, repetitions, and fillers. "
                "Return timestamped spoken units, generally 3 to 12 seconds each. Timestamps are "
                "seconds from the beginning of the audio. Exclude silence and do not summarize, "
                "translate, censor, or invent speech. Set language to the dominant BCP-47 language "
                "tag, such as zh-TW. Return only data matching the supplied schema."
            )
            response = client.models.generate_content(
                model=self.asr_model,
                contents=[uploaded, prompt],
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": TranscriptDocument.model_json_schema(),
                    "temperature": 0,
                    "max_output_tokens": 16384,
                },
            )
            (recording_dir / "transcript.raw.json").write_text(
                response.text, encoding="utf-8"
            )
            document = TranscriptDocument.model_validate_json(response.text)
            normalized = self._normalize_asr_segments(
                [segment.model_dump() for segment in document.segments],
                float(recording["duration_seconds"]),
            )
            segments = self._validate_segments(
                normalized,
                float(recording["duration_seconds"]),
            )
            if not segments:
                raise RuntimeError("ASR returned no speech segments")
            return {"language": document.language, "segments": segments}
        finally:
            if getattr(uploaded, "name", None):
                try:
                    client.files.delete(name=uploaded.name)
                except Exception:
                    pass

    def _wait_for_uploaded_file(self, client, uploaded):
        for _ in range(60):
            state = getattr(getattr(uploaded, "state", None), "name", None)
            if state in (None, "ACTIVE"):
                return uploaded
            if state == "FAILED":
                raise RuntimeError("ASR audio upload processing failed")
            time.sleep(1)
            uploaded = client.files.get(name=uploaded.name)
        raise RuntimeError("Timed out waiting for ASR audio upload")

    def _normalize_asr_segments(self, segments: list[dict], duration: float) -> list[dict]:
        # Some multimodal models emit seconds within the current minute even when the
        # schema requests absolute seconds. Preserve response order and unwrap those resets.
        unwrapped = []
        minute_offset = 0.0
        previous_start = 0.0
        for raw in segments:
            unit = TranscriptUnit.model_validate(raw)
            start = unit.start + minute_offset
            while start < previous_start - 15.0:
                minute_offset += 60.0
                start = unit.start + minute_offset
            end = unit.end + minute_offset
            while end < start:
                end += 60.0
            unwrapped.append({"start": start, "end": end, "text": unit.text})
            previous_start = start

        normalized = []
        for index, raw in enumerate(unwrapped):
            unit = TranscriptUnit.model_validate(raw)
            start = min(unit.start, duration)
            end = min(unit.end, duration)
            if end <= start and start < duration:
                later_starts = [
                    float(item["start"])
                    for item in unwrapped[index + 1 :]
                    if float(item["start"]) > start
                ]
                inferred_end = later_starts[0] if later_starts else start + 1.0
                end = min(inferred_end, duration)
            normalized.append({"start": start, "end": end, "text": unit.text})
        return normalized

    def _segment_transcript(self, segments: list[dict]) -> list[dict]:
        if not self.gemini_api_key or not segments:
            return segments

        client = genai.Client(api_key=self.gemini_api_key)
        prompt = (
            "Group adjacent timestamped transcript units into short, semantically meaningful, "
            "reorderable spoken segments. Preserve every original word in the same order. You may "
            "only merge adjacent units; do not split a unit, rewrite, translate, add content, "
            "create overlaps, or bridge timestamp gaps. Use the first merged unit's start and the "
            "last merged unit's end. Return only data matching the supplied schema.\n\n"
            "Transcript:\n"
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
            candidate = [segment.model_dump() for segment in result.segments]
            self._assert_text_preserved(segments, candidate)
            return candidate
        except Exception:
            # ASR output remains directly usable during segmentation model outages.
            return segments

    def _validate_segments(
        self,
        segments: list[dict],
        duration: float,
        expected_text: list[dict] | None = None,
    ) -> list[dict]:
        validated = []
        previous_end = 0.0
        for raw in sorted(segments, key=lambda item: (float(item["start"]), float(item["end"]))):
            unit = TranscriptUnit.model_validate(raw)
            start = round(unit.start, 3)
            end = round(min(unit.end, duration), 3)
            text = unit.text.strip()
            if end <= start:
                raise ValueError(f"Invalid transcript timestamp range: {start}-{end}")
            if start < previous_end - 0.01:
                raise ValueError("Transcript segments overlap")
            validated.append({"start": start, "end": end, "text": text})
            previous_end = end
        if expected_text is not None:
            self._assert_text_preserved(expected_text, validated)
        return validated

    def _assert_text_preserved(self, source: list[dict], candidate: list[dict]) -> None:
        def normalize(units: list[dict]) -> str:
            return re.sub(r"\s+", "", "".join(str(unit["text"]).strip() for unit in units))

        if normalize(source) != normalize(candidate):
            raise ValueError("Transcript segmentation changed the spoken text")

    def _store_segments(self, recording_id: str, recording: dict, segments: list[dict]) -> None:
        recording_dir = self._recording_dir(recording)
        segment_dir = recording_dir / "segments"
        segment_dir.mkdir(parents=True, exist_ok=True)
        stored = []
        with self.database.connection() as connection:
            connection.execute("DELETE FROM segments WHERE recording_id = ?", (recording_id,))
            for index, segment in enumerate(segments, start=1):
                segment_id = f"{recording_id}_seg_{index:03d}"
                segment_path = None
                if self.ffmpeg_available and recording["video_path"]:
                    output = segment_dir / f"{segment_id}.mp4"
                    self._run_ffmpeg(
                        [
                            "ffmpeg",
                            "-hide_banner",
                            "-loglevel",
                            "error",
                            "-y",
                            "-ss",
                            str(segment["start"]),
                            "-to",
                            str(segment["end"]),
                            "-i",
                            recording["video_path"],
                            "-c:v",
                            "libx264",
                            "-preset",
                            "fast",
                            "-crf",
                            "20",
                            "-c:a",
                            "aac",
                            "-movflags",
                            "+faststart",
                            str(output),
                        ],
                        f"Video extraction failed for segment {index}",
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
            json.dumps({"segments": stored}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (recording_dir / "processed_at.txt").write_text(now_iso(), encoding="utf-8")

    def render_timeline(self, recording_id: str, timeline: list[str]) -> dict:
        if not self.ffmpeg_available:
            raise RuntimeError("Timeline rendering requires ffmpeg")
        with self.database.connection() as connection:
            recording_row = connection.execute(
                "SELECT * FROM recordings WHERE recording_id = ?", (recording_id,)
            ).fetchone()
            if not recording_row:
                raise LookupError("Recording not found")
            segment_rows = connection.execute(
                "SELECT * FROM segments WHERE recording_id = ? ORDER BY sequence_number",
                (recording_id,),
            ).fetchall()

        recording = dict(recording_row)
        segments = {row["segment_id"]: dict(row) for row in segment_rows}
        if recording["processing_status"] != "ready":
            raise ValueError("Recording must be processed before rendering a timeline")
        if len(timeline) != len(segments) or len(set(timeline)) != len(timeline):
            raise ValueError("Timeline must contain every segment exactly once")
        if set(timeline) != set(segments):
            raise ValueError("Timeline contains unknown or missing segment IDs")
        if not recording["video_path"] or not Path(recording["video_path"]).exists():
            raise RuntimeError("Recording media is missing")

        digest = hashlib.sha256("\n".join(timeline).encode()).hexdigest()[:16]
        render_id = f"render_{recording_id}_{digest}"
        render_dir = self._recording_dir(recording) / "timeline_renders"
        render_dir.mkdir(parents=True, exist_ok=True)
        output = render_dir / f"{render_id}.mp4"
        duration = round(
            sum(segments[item]["end_time"] - segments[item]["start_time"] for item in timeline),
            3,
        )

        if not output.exists():
            filters = []
            concat_inputs = []
            for index, segment_id in enumerate(timeline):
                segment = segments[segment_id]
                filters.append(
                    f"[0:v]trim=start={segment['start_time']}:end={segment['end_time']},"
                    f"setpts=PTS-STARTPTS[v{index}]"
                )
                filters.append(
                    f"[0:a]atrim=start={segment['start_time']}:end={segment['end_time']},"
                    f"asetpts=PTS-STARTPTS[a{index}]"
                )
                concat_inputs.append(f"[v{index}][a{index}]")
            filters.append(
                "".join(concat_inputs)
                + f"concat=n={len(timeline)}:v=1:a=1[outv][outa]"
            )
            self._run_ffmpeg(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    recording["video_path"],
                    "-filter_complex",
                    ";".join(filters),
                    "-map",
                    "[outv]",
                    "-map",
                    "[outa]",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "20",
                    "-c:a",
                    "aac",
                    "-movflags",
                    "+faststart",
                    str(output),
                ],
                "Timeline rendering failed",
            )

        created_at = now_iso()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO timeline_renders VALUES (?, ?, ?, ?, ?, ?)",
                (
                    render_id,
                    recording_id,
                    json.dumps(timeline),
                    str(output),
                    duration,
                    created_at,
                ),
            )
        manifest = {
            "render_id": render_id,
            "recording_id": recording_id,
            "timeline": timeline,
            "duration_seconds": duration,
            "created_at": created_at,
        }
        (render_dir / f"{render_id}.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        return {key: manifest[key] for key in manifest if key != "created_at"}

    def _run_ffmpeg(self, command: list[str], message: str) -> None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (
                result.stderr.strip().splitlines()[-1]
                if result.stderr.strip()
                else "unknown error"
            )
            raise RuntimeError(f"{message}: {detail}")
