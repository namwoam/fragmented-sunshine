import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    object_id TEXT PRIMARY KEY,
    class_name TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recordings (
    recording_id TEXT PRIMARY KEY,
    object_id TEXT NOT NULL REFERENCES objects(object_id),
    video_path TEXT,
    audio_path TEXT,
    duration_seconds REAL NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    processing_status TEXT NOT NULL,
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS segments (
    segment_id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    transcript_text TEXT NOT NULL,
    video_segment_path TEXT,
    sequence_number INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS playback_events (
    playback_event_id TEXT PRIMARY KEY,
    recording_id TEXT NOT NULL REFERENCES recordings(recording_id),
    object_id TEXT NOT NULL REFERENCES objects(object_id),
    replay_count INTEGER NOT NULL,
    timeline_order TEXT NOT NULL,
    played_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def seed_objects(self) -> None:
        defaults = (
            ("plush_01", "plush_toy", "Plush toy"),
            ("card_01", "handwritten_card", "Handwritten card"),
            ("perfume_01", "perfume_bottle", "Perfume bottle"),
        )
        with self.connection() as connection:
            connection.executemany(
                "INSERT OR IGNORE INTO objects VALUES (?, ?, ?, ?)",
                [
                    (object_id, class_name, name, now_iso())
                    for object_id, class_name, name in defaults
                ],
            )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def row_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    if "timeline_order" in result:
        result["timeline"] = json.loads(result.pop("timeline_order"))
    return result
