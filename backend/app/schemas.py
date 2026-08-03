from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ObjectCreate(BaseModel):
    object_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$", max_length=80)
    class_name: str = Field(min_length=1, max_length=120)
    display_name: str = Field(min_length=1, max_length=120)
    location_x: float | None = Field(default=None, ge=0, le=1)
    location_y: float | None = Field(default=None, ge=0, le=1)
    touch_radius: float = Field(default=0.08, ge=0.02, le=0.3)


class ObjectResponse(ObjectCreate):
    created_at: datetime


class ObjectLocationUpdate(BaseModel):
    location_x: float = Field(ge=0, le=1)
    location_y: float = Field(ge=0, le=1)
    touch_radius: float = Field(default=0.08, ge=0.02, le=0.3)


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


class TimelineRenderCreate(BaseModel):
    timeline: list[str] = Field(min_length=1)


class TimelineRenderResponse(BaseModel):
    render_id: str
    recording_id: str
    timeline: list[str]
    duration_seconds: float
    media_url: str


class TranscriptSegmentResponse(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    language: str
    segments: list[TranscriptSegmentResponse]


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
    touch_x: float
    touch_y: float


class ObjectDetection(BaseModel):
    object_id: str | None
    class_name: str
    confidence: float
    bbox: BoundingBox
    on_tray: bool


class DwellProgress(BaseModel):
    object_id: str
    handedness: str
    elapsed_seconds: float
    remaining_seconds: float
    progress: float


class InteractionLock(BaseModel):
    object_id: str
    handedness: str
    status: Literal["live", "hand_locked", "activated"]
    object_visible: bool


class VisionEvent(BaseModel):
    event_type: str
    timestamp: float
    frame_image: str | None = None
    object_id: str | None = None
    handedness: str | None = None
    hands: list[HandDetection] = Field(default_factory=list)
    objects: list[ObjectDetection] = Field(default_factory=list)
    dwells: list[DwellProgress] = Field(default_factory=list)
    locks: list[InteractionLock] = Field(default_factory=list)
