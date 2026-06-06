import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import get_settings
from .database import Database, now_iso, row_dict
from .schemas import ObjectCreate, PlaybackEventCreate, VisionEvent
from .services import ProcessingService
from .timeline import reorder_segments
from .vision_hub import VisionEventHub

settings = get_settings()
database = Database(settings.database_path)
processor = ProcessingService(
    database,
    settings.data_dir,
    gemini_api_key=settings.gemini_api_key,
    gemini_model=settings.gemini_model,
)
vision_hub = VisionEventHub()


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.initialize()
    database.seed_objects()
    yield


app = FastAPI(title="Fragmented Sunshine API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/vision/events", status_code=202)
async def publish_vision_event(event: VisionEvent):
    await vision_hub.publish(event.model_dump())
    return {"accepted": True}


@app.websocket("/api/vision/events")
async def vision_events(websocket: WebSocket):
    await websocket.accept()
    queue = vision_hub.subscribe()
    try:
        while True:
            await websocket.send_json(await queue.get())
    except WebSocketDisconnect:
        pass
    finally:
        vision_hub.unsubscribe(queue)


def save_upload(upload: UploadFile | None, destination: Path) -> str | None:
    if upload is None or not upload.filename:
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return str(destination)


def serialize_segment(row) -> dict:
    segment = dict(row)
    segment["media_url"] = (
        f"/api/segments/{segment['segment_id']}/media" if segment["video_segment_path"] else None
    )
    return segment


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "ffmpeg_available": processor.ffmpeg_available,
        "gemini_configured": bool(settings.gemini_api_key),
        "gemini_model": settings.gemini_model,
        "data_dir": str(settings.data_dir),
    }


@app.get("/api/objects")
def list_objects():
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM objects ORDER BY created_at, display_name"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/objects", status_code=201)
def create_object(payload: ObjectCreate):
    with database.connection() as connection:
        existing = connection.execute(
            "SELECT 1 FROM objects WHERE object_id = ?", (payload.object_id,)
        ).fetchone()
        if existing:
            raise HTTPException(409, "Object ID already exists")
        created_at = now_iso()
        connection.execute(
            "INSERT INTO objects VALUES (?, ?, ?, ?)",
            (payload.object_id, payload.class_name, payload.display_name, created_at),
        )
    return {**payload.model_dump(), "created_at": created_at}


@app.get("/api/objects/{object_id}")
def get_object(object_id: str):
    with database.connection() as connection:
        object_row = connection.execute(
            "SELECT * FROM objects WHERE object_id = ?", (object_id,)
        ).fetchone()
        if not object_row:
            raise HTTPException(404, "Object not found")
        recordings = connection.execute(
            "SELECT recording_id, duration_seconds, created_at, processing_status FROM recordings "
            "WHERE object_id = ? ORDER BY created_at DESC",
            (object_id,),
        ).fetchall()
    return {**dict(object_row), "recordings": [dict(row) for row in recordings]}


@app.post("/api/recordings", status_code=201)
def create_recording(
    object_id: str = Form(),
    started_at: datetime = Form(),
    ended_at: datetime = Form(),
    video_file: UploadFile = File(),
    audio_file: UploadFile | None = File(default=None),
):
    with database.connection() as connection:
        if not connection.execute(
            "SELECT 1 FROM objects WHERE object_id = ?", (object_id,)
        ).fetchone():
            raise HTTPException(404, "Object not found")

    recording_id = f"rec_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    recording_dir = settings.data_dir / "objects" / object_id / "recordings" / recording_id
    suffix = Path(video_file.filename or "recording.webm").suffix or ".webm"
    video_path = save_upload(video_file, recording_dir / f"original{suffix}")
    audio_path = save_upload(audio_file, recording_dir / "audio.webm")
    duration = max((ended_at - started_at).total_seconds(), 0)
    created_at = now_iso()
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO recordings VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                recording_id,
                object_id,
                video_path,
                audio_path,
                duration,
                started_at.isoformat(),
                ended_at.isoformat(),
                created_at,
                "uploaded",
                None,
            ),
        )
    return {
        "recording_id": recording_id,
        "object_id": object_id,
        "duration_seconds": duration,
        "processing_status": "uploaded",
    }


@app.post("/api/recordings/{recording_id}/process")
def process_recording(recording_id: str):
    try:
        processor.process(recording_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, f"Processing failed: {exc}") from exc
    return get_recording(recording_id)


@app.get("/api/recordings/{recording_id}")
def get_recording(recording_id: str):
    with database.connection() as connection:
        row = connection.execute(
            "SELECT * FROM recordings WHERE recording_id = ?", (recording_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Recording not found")
        segments = connection.execute(
            "SELECT * FROM segments WHERE recording_id = ? ORDER BY sequence_number",
            (recording_id,),
        ).fetchall()
    recording = dict(row)
    recording["video_url"] = (
        f"/api/recordings/{recording_id}/media" if recording["video_path"] else None
    )
    recording["segments"] = [serialize_segment(segment) for segment in segments]
    return recording


@app.get("/api/recordings/{recording_id}/media")
def recording_media(recording_id: str):
    with database.connection() as connection:
        row = connection.execute(
            "SELECT video_path FROM recordings WHERE recording_id = ?", (recording_id,)
        ).fetchone()
    if not row or not row["video_path"] or not Path(row["video_path"]).exists():
        raise HTTPException(404, "Media not found")
    return FileResponse(row["video_path"])


@app.get("/api/segments/{segment_id}/media")
def segment_media(segment_id: str):
    with database.connection() as connection:
        row = connection.execute(
            "SELECT video_segment_path FROM segments WHERE segment_id = ?", (segment_id,)
        ).fetchone()
    if not row or not row["video_segment_path"] or not Path(row["video_segment_path"]).exists():
        raise HTTPException(404, "Segment media not found")
    return FileResponse(row["video_segment_path"])


@app.get("/api/objects/{object_id}/playback")
def get_playback(object_id: str):
    with database.connection() as connection:
        recording = connection.execute(
            "SELECT * FROM recordings WHERE object_id = ? AND processing_status = 'ready' "
            "ORDER BY created_at DESC LIMIT 1",
            (object_id,),
        ).fetchone()
        if not recording:
            raise HTTPException(404, "No processed recording for this object")
        segments = connection.execute(
            "SELECT * FROM segments WHERE recording_id = ? ORDER BY sequence_number",
            (recording["recording_id"],),
        ).fetchall()
        event_count = connection.execute(
            "SELECT COUNT(*) FROM playback_events WHERE recording_id = ?",
            (recording["recording_id"],),
        ).fetchone()[0]
    replay_count = event_count + 1
    serialized = [serialize_segment(segment) for segment in segments]
    timeline = reorder_segments([segment["segment_id"] for segment in serialized], replay_count)
    return {
        "object_id": object_id,
        "recording_id": recording["recording_id"],
        "replay_count": replay_count,
        "timeline": timeline,
        "segments": serialized,
        "source_url": f"/api/recordings/{recording['recording_id']}/media",
    }


@app.post("/api/objects/{object_id}/playback-events", status_code=201)
def create_playback_event(object_id: str, payload: PlaybackEventCreate):
    with database.connection() as connection:
        recording = connection.execute(
            "SELECT object_id FROM recordings WHERE recording_id = ?", (payload.recording_id,)
        ).fetchone()
        if not recording or recording["object_id"] != object_id:
            raise HTTPException(404, "Recording not found for object")
        replay_count = (
            connection.execute(
                "SELECT COUNT(*) FROM playback_events WHERE recording_id = ?",
                (payload.recording_id,),
            ).fetchone()[0]
            + 1
        )
        event_id = f"play_{uuid4().hex}"
        connection.execute(
            "INSERT INTO playback_events VALUES (?, ?, ?, ?, ?, ?)",
            (
                event_id,
                payload.recording_id,
                object_id,
                replay_count,
                json.dumps(payload.timeline),
                payload.played_at.isoformat(),
            ),
        )
    return {"playback_event_id": event_id, "replay_count": replay_count}


@app.get("/api/objects/{object_id}/playback-events")
def list_playback_events(object_id: str):
    with database.connection() as connection:
        rows = connection.execute(
            "SELECT * FROM playback_events WHERE object_id = ? ORDER BY played_at DESC",
            (object_id,),
        ).fetchall()
    return [row_dict(row) for row in rows]
