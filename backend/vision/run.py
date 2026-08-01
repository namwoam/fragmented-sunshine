import json
import secrets
import threading
from pathlib import Path
from typing import Annotated

import click
import cv2
import mediapipe as mp
import numpy as np
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .objects import ObjectDetector

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class RegisteredObject(BaseModel):
    object_id: str = Field(min_length=1, max_length=80)
    class_name: str = Field(min_length=1, max_length=120)


class HandTracker:
    def __init__(self, model_path: str, swap_handedness: bool = False):
        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=model_path),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.55,
            min_hand_presence_confidence=0.55,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp.tasks.vision.HandLandmarker.create_from_options(options)
        self.swap_handedness = swap_handedness
        self.previous_wrists: dict[str, tuple[float, float, float]] = {}

    def detect(self, rgb_frame, timestamp: float) -> list[dict]:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.landmarker.detect_for_video(image, int(timestamp * 1000))
        hands = []
        for landmarks, categories in zip(result.hand_landmarks, result.handedness, strict=True):
            category = categories[0]
            handedness = category.category_name.lower()
            if self.swap_handedness:
                handedness = "right" if handedness == "left" else "left"
            xs = [landmark.x for landmark in landmarks]
            ys = [landmark.y for landmark in landmarks]
            wrist = landmarks[0]
            touch = landmarks[8]
            previous = self.previous_wrists.get(handedness)
            movement_x = movement_y = speed = 0.0
            if previous and timestamp > previous[2]:
                elapsed = timestamp - previous[2]
                movement_x = wrist.x - previous[0]
                movement_y = wrist.y - previous[1]
                speed = ((movement_x**2 + movement_y**2) ** 0.5) / elapsed
            self.previous_wrists[handedness] = (wrist.x, wrist.y, timestamp)
            hands.append(
                {
                    "handedness": handedness,
                    "confidence": category.score,
                    "bbox": {
                        "x1": max(0.0, min(xs)),
                        "y1": max(0.0, min(ys)),
                        "x2": min(1.0, max(xs)),
                        "y2": min(1.0, max(ys)),
                    },
                    "wrist_x": wrist.x,
                    "wrist_y": wrist.y,
                    "movement_x": movement_x,
                    "movement_y": movement_y,
                    "speed": speed,
                    "touch_x": touch.x,
                    "touch_y": touch.y,
                }
            )
        return hands

    def close(self) -> None:
        self.landmarker.close()


class InferenceEngine:
    def __init__(self, hand_tracker: HandTracker, object_detector: ObjectDetector):
        self.hand_tracker = hand_tracker
        self.object_detector = object_detector
        self.lock = threading.Lock()

    def infer(self, frame, timestamp: float, registrations: list[dict]) -> dict:
        with self.lock:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            hands = self.hand_tracker.detect(rgb, timestamp)
            objects = self.object_detector.detect(frame, registrations)
        return {"timestamp": timestamp, "hands": hands, "objects": objects}

    def close(self) -> None:
        self.hand_tracker.close()


def create_app(engine: InferenceEngine, token: str | None = None) -> FastAPI:
    app = FastAPI(title="Fragmented Sunshine Remote Vision")

    @app.get("/health")
    def health():
        return {"status": "ok", "inference": "ready"}

    @app.post("/infer")
    async def infer(
        frame: Annotated[UploadFile, File()],
        timestamp: Annotated[float, Form()],
        objects: Annotated[str, Form()],
        authorization: Annotated[str | None, Header()] = None,
    ):
        if token:
            expected = f"Bearer {token}"
            if authorization is None or not secrets.compare_digest(authorization, expected):
                raise HTTPException(401, "Invalid inference token")

        payload = await frame.read()
        if not payload or len(payload) > 10 * 1024 * 1024:
            raise HTTPException(413, "Frame must be between 1 byte and 10 MB")
        decoded = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise HTTPException(422, "Frame is not a valid image")
        try:
            registrations = [
                item.model_dump()
                for item in [RegisteredObject.model_validate(item) for item in json.loads(objects)]
            ]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise HTTPException(422, "Objects must be a valid registered-object list") from exc
        return engine.infer(decoded, timestamp, registrations)

    return app


@click.command(help="Serve MediaPipe and YOLO inference for laptop camera clients.")
@click.option(
    "--host",
    envvar="VISION_INFERENCE_HOST",
    default="0.0.0.0",
    show_default=True,
)
@click.option(
    "--port",
    type=click.IntRange(1, 65535),
    envvar="VISION_INFERENCE_PORT",
    default=8010,
    show_default=True,
)
@click.option(
    "--hand-model",
    envvar="HAND_LANDMARKER_MODEL",
    default="models/hand_landmarker.task",
    show_default=True,
)
@click.option(
    "--object-model",
    envvar="YOLO_WORLD_MODEL",
    default="yolov8m-worldv2.pt",
    show_default=True,
)
@click.option(
    "--object-confidence",
    type=click.FloatRange(0, 1),
    envvar="YOLO_WORLD_CONFIDENCE",
    default=0.10,
    show_default=True,
)
@click.option(
    "--object-iou",
    type=click.FloatRange(0, 1),
    envvar="YOLO_WORLD_IOU",
    default=0.5,
    show_default=True,
)
@click.option("--object-device", envvar="YOLO_WORLD_DEVICE", default=None)
@click.option("--swap-handedness", is_flag=True)
@click.option("--token", envvar="VISION_INFERENCE_TOKEN", default=None)
def main(
    host: str,
    port: int,
    hand_model: str,
    object_model: str,
    object_confidence: float,
    object_iou: float,
    object_device: str | None,
    swap_handedness: bool,
    token: str | None,
) -> None:
    hand_model_path = Path(hand_model)
    if not hand_model_path.exists():
        raise click.ClickException(
            f"MediaPipe model not found: {hand_model_path}. Run `task vision:models`."
        )
    engine = InferenceEngine(
        HandTracker(str(hand_model_path), swap_handedness),
        ObjectDetector(
            model_path=object_model,
            confidence=object_confidence,
            iou=object_iou,
            device=object_device,
        ),
    )
    click.echo(f"Remote vision listening on http://{host}:{port}")
    try:
        uvicorn.run(create_app(engine, token), host=host, port=port)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
