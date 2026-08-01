import base64
import json
import time
from pathlib import Path

import click
import cv2
import httpx
from dotenv import load_dotenv
from pydantic import BaseModel

from app.schemas import HandDetection, ObjectDetection

from .cameras import CAMERA_SOURCE
from .interactions import InteractionStateManager

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class InferenceResult(BaseModel):
    timestamp: float
    hands: list[HandDetection]
    objects: list[ObjectDetection]


class RegisteredObjects:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.items: list[dict] = []
        self.last_refresh = 0.0

    def get(self, client: httpx.Client, now: float) -> list[dict]:
        if now - self.last_refresh < 2.0:
            return self.items
        self.last_refresh = now
        try:
            response = client.get(f"{self.api_url}/api/objects", timeout=1)
            response.raise_for_status()
            self.items = [
                {"object_id": item["object_id"], "class_name": item["class_name"]}
                for item in response.json()
            ]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            pass
        return self.items


def infer(
    client: httpx.Client,
    inference_url: str,
    token: str | None,
    timeout: float,
    timestamp: float,
    frame_jpeg: bytes,
    registrations: list[dict],
) -> InferenceResult:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post(
        f"{inference_url.rstrip('/')}/infer",
        headers=headers,
        data={"timestamp": str(timestamp), "objects": json.dumps(registrations)},
        files={"frame": ("tray.jpg", frame_jpeg, "image/jpeg")},
        timeout=timeout,
    )
    response.raise_for_status()
    return InferenceResult.model_validate(response.json())


def publish(client: httpx.Client, api_url: str, event: dict) -> None:
    try:
        client.post(
            f"{api_url.rstrip('/')}/api/vision/events",
            json=event,
            timeout=1,
        ).raise_for_status()
    except httpx.HTTPError:
        pass


def encode_jpeg(frame, quality: int) -> bytes | None:
    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )
    return encoded.tobytes() if success else None


def encode_preview(frame, quality: int) -> str | None:
    jpeg = encode_jpeg(frame, quality)
    if jpeg is None:
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(jpeg).decode('ascii')}"


def draw_preview(frame, hands: list[dict], objects: list[dict]) -> None:
    height, width = frame.shape[:2]
    for item in [*hands, *objects]:
        box = item["bbox"]
        color = (60, 180, 255) if "handedness" in item else (120, 220, 120)
        cv2.rectangle(
            frame,
            (int(box["x1"] * width), int(box["y1"] * height)),
            (int(box["x2"] * width), int(box["y2"] * height)),
            color,
            2,
        )
        label = item.get("handedness") or item.get("object_id") or item["class_name"]
        cv2.putText(
            frame,
            label,
            (int(box["x1"] * width), int(box["y1"] * height) - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1,
        )
        if "handedness" in item:
            cv2.circle(
                frame,
                (int(item["touch_x"] * width), int(item["touch_y"] * height)),
                7,
                color,
                -1,
            )
    cv2.imshow("Fragmented Sunshine - Camera Client", frame)


@click.command(help="Send laptop camera frames to a remote vision inference service.")
@click.option(
    "--camera",
    type=CAMERA_SOURCE,
    envvar="TRAY_CAMERA_INDEX",
    default="0",
    show_default=True,
)
@click.option(
    "--recording-camera",
    type=CAMERA_SOURCE,
    envvar="RECORDING_CAMERA_INDEX",
    default="1",
    show_default=True,
)
@click.option(
    "--api",
    envvar="VISION_API_URL",
    default="http://localhost:8000",
    show_default=True,
)
@click.option(
    "--inference-url",
    envvar="VISION_INFERENCE_URL",
    default="http://localhost:8010",
    show_default=True,
)
@click.option("--token", envvar="VISION_INFERENCE_TOKEN", default=None)
@click.option(
    "--timeout",
    type=click.FloatRange(min=0.1),
    envvar="VISION_INFERENCE_TIMEOUT_SECONDS",
    default=5.0,
    show_default=True,
)
@click.option(
    "--fps",
    type=click.FloatRange(min=0.1),
    envvar="VISION_CAMERA_FPS",
    default=12.0,
    show_default=True,
)
@click.option(
    "--jpeg-quality",
    type=click.IntRange(1, 100),
    envvar="VISION_CAMERA_JPEG_QUALITY",
    default=80,
    show_default=True,
)
@click.option(
    "--preview-quality",
    type=click.IntRange(1, 100),
    default=65,
    show_default=True,
)
@click.option(
    "--dwell-seconds",
    type=click.FloatRange(min=0, min_open=True),
    default=3.0,
    show_default=True,
)
@click.option("--preview", is_flag=True)
def main(
    camera: str | int,
    recording_camera: str | int,
    api: str,
    inference_url: str,
    token: str | None,
    timeout: float,
    fps: float,
    jpeg_quality: int,
    preview_quality: int,
    dwell_seconds: float,
    preview: bool,
) -> None:
    interactions = InteractionStateManager(dwell_seconds)
    registrations = RegisteredObjects(api)
    tray_capture = cv2.VideoCapture(camera)
    tray_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not tray_capture.isOpened():
        raise click.ClickException(f"Could not open tray camera {camera}")
    recording_capture = cv2.VideoCapture(recording_camera)
    recording_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not recording_capture.isOpened():
        recording_capture.release()
        recording_capture = None
        click.echo(
            f"Warning: could not open recording camera {recording_camera}; "
            "the recording debug feed will be unavailable.",
            err=True,
        )

    interval = 1 / fps
    last_success = time.monotonic()
    last_error_report = 0.0
    with httpx.Client() as client:
        try:
            while True:
                loop_started = time.monotonic()
                success, frame = tray_capture.read()
                if not success:
                    time.sleep(interval)
                    continue
                timestamp = time.time()
                frame_jpeg = encode_jpeg(frame, jpeg_quality)
                if frame_jpeg is None:
                    continue

                hands: list[dict] = []
                objects: list[dict] = []
                events: list[dict] = []
                try:
                    result = infer(
                        client,
                        inference_url,
                        token,
                        timeout,
                        timestamp,
                        frame_jpeg,
                        registrations.get(client, loop_started),
                    )
                    hands = [item.model_dump() for item in result.hands]
                    objects = [item.model_dump() for item in result.objects]
                    events = interactions.update(timestamp, hands, objects)
                    last_success = time.monotonic()
                except (httpx.HTTPError, ValueError) as exc:
                    now = time.monotonic()
                    if now - last_success >= 2.0:
                        events = interactions.update(timestamp, [], [])
                    if now - last_error_report >= 5.0:
                        click.echo(f"Remote inference unavailable: {exc}", err=True)
                        last_error_report = now

                publish(
                    client,
                    api,
                    {
                        "event_type": "frame",
                        "timestamp": timestamp,
                        "frame_image": encode_preview(frame, preview_quality),
                        "hands": hands,
                        "objects": objects,
                        "dwells": interactions.progress(timestamp),
                    },
                )
                if recording_capture is not None:
                    recording_success, recording_frame = recording_capture.read()
                    if recording_success:
                        publish(
                            client,
                            api,
                            {
                                "event_type": "recording_frame",
                                "timestamp": timestamp,
                                "frame_image": encode_preview(recording_frame, preview_quality),
                            },
                        )
                for event in events:
                    publish(client, api, {**event, "hands": hands, "objects": objects})
                if preview:
                    draw_preview(frame, hands, objects)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                time.sleep(max(0.0, interval - (time.monotonic() - loop_started)))
        finally:
            tray_capture.release()
            if recording_capture is not None:
                recording_capture.release()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
