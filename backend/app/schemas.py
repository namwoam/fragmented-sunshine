from datetime import datetime

from pydantic import BaseModel, Field


class ObjectCreate(BaseModel):
    object_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=80)
    class_name: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)


class ObjectResponse(ObjectCreate):
    created_at: datetime


class SegmentResponse(BaseModel):
    segment_id: str
    recording_id: str
    start_time: float
    end_time: float
    transcript_text: str
    video_segment_path: str | None = None
    sequence_number: int
    media_url: str | None = None


class RecordingResponse(BaseModel):
    recording_id: str
    object_id: str
    duration_seconds: float
    started_at: datetime
    ended_at: datetime
    created_at: datetime
    processing_status: str
    error_message: str | None = None
    video_url: str | None = None
    segments: list[SegmentResponse] = Field(default_factory=list)


class PlaybackResponse(BaseModel):
    object_id: str
    recording_id: str
    replay_count: int
    timeline: list[str]
    segments: list[SegmentResponse]
    source_url: str | None = None


class PlaybackEventCreate(BaseModel):
    recording_id: str
    timeline: list[str]
    played_at: datetime


class BoundingBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class HandDetection(BaseModel):
    handedness: str
    confidence: float
    bbox: BoundingBox
    wrist_x: float
    wrist_y: float
    movement_x: float
    movement_y: float
    speed: float


class ObjectDetection(BaseModel):
    object_id: str | None
    class_name: str
    confidence: float
    bbox: BoundingBox
    on_tray: bool


class VisionEvent(BaseModel):
    event_type: str
    timestamp: float
    object_id: str | None = None
    handedness: str | None = None
    hands: list[HandDetection] = Field(default_factory=list)
    objects: list[ObjectDetection] = Field(default_factory=list)
