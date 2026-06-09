import argparse
import base64
import os
import time
from pathlib import Path

import cv2
import httpx
import mediapipe as mp

from .interactions import InteractionStateManager


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tray hand and object vision service")
    parser.add_argument("--camera", type=int, default=int(os.getenv("TRAY_CAMERA_INDEX", "0")))
    parser.add_argument(
        "--recording-camera",
        type=int,
        default=int(os.getenv("RECORDING_CAMERA_INDEX", "1")),
        help="Camera index streamed to the recording-camera debug feed",
    )
    parser.add_argument("--api", default=os.getenv("VISION_API_URL", "http://localhost:8000"))
    parser.add_argument(
        "--hand-model",
        default=os.getenv("HAND_LANDMARKER_MODEL", "models/hand_landmarker.task"),
    )
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--preview-quality", type=int, default=65)
    parser.add_argument("--dwell-seconds", type=float, default=5.0)
    parser.add_argument("--swap-handedness", action="store_true")
    parser.add_argument("--preview", action="store_true")
    return parser.parse_args()


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


class ObjectLocations:
    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.objects: list[dict] = []
        self.last_refresh = 0.0

    def get(self, client: httpx.Client, timestamp: float) -> list[dict]:
        if timestamp - self.last_refresh >= 2.0 or not self.objects:
            try:
                response = client.get(f"{self.api_url}/api/objects", timeout=1)
                response.raise_for_status()
                self.objects = [
                    item
                    for item in response.json()
                    if item.get("location_x") is not None and item.get("location_y") is not None
                ]
                self.last_refresh = timestamp
            except httpx.HTTPError:
                pass
        return [self._as_detection(item) for item in self.objects]

    @staticmethod
    def _as_detection(item: dict) -> dict:
        radius = item.get("touch_radius", 0.08)
        x = item["location_x"]
        y = item["location_y"]
        return {
            **item,
            "confidence": 1.0,
            "bbox": {
                "x1": max(0.0, x - radius),
                "y1": max(0.0, y - radius),
                "x2": min(1.0, x + radius),
                "y2": min(1.0, y + radius),
            },
            "on_tray": True,
        }


def publish(client: httpx.Client, api_url: str, event: dict) -> None:
    try:
        client.post(
            f"{api_url.rstrip('/')}/api/vision/events", json=event, timeout=1
        ).raise_for_status()
    except httpx.HTTPError:
        pass


def encode_preview(frame, quality: int) -> str | None:
    success, encoded = cv2.imencode(
        ".jpg",
        frame,
        [cv2.IMWRITE_JPEG_QUALITY, max(1, min(quality, 100))],
    )
    if not success:
        return None
    return f"data:image/jpeg;base64,{base64.b64encode(encoded).decode('ascii')}"


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
    cv2.imshow("Fragmented Sunshine - Tray Vision", frame)


def main() -> None:
    args = parse_args()
    hand_model = Path(args.hand_model)
    if not hand_model.exists():
        raise SystemExit(f"MediaPipe model not found: {hand_model}. Run `task vision:models`.")
    hand_tracker = HandTracker(str(hand_model), args.swap_handedness)
    object_locations = ObjectLocations(args.api)
    interactions = InteractionStateManager(args.dwell_seconds)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit(f"Could not open tray camera {args.camera}")
    recording_camera = cv2.VideoCapture(args.recording_camera)
    if not recording_camera.isOpened():
        recording_camera.release()
        recording_camera = None
        print(
            f"Warning: could not open recording camera {args.recording_camera}; "
            "the recording debug feed will be unavailable."
        )

    interval = 1 / args.fps
    with httpx.Client() as client:
        try:
            while True:
                loop_started = time.monotonic()
                success, frame = camera.read()
                if not success:
                    time.sleep(interval)
                    continue
                timestamp = time.time()
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                hands = hand_tracker.detect(rgb, timestamp)
                objects = object_locations.get(client, timestamp)
                events = interactions.update(timestamp, hands, objects)
                base = {
                    "timestamp": timestamp,
                    "frame_image": encode_preview(frame, args.preview_quality),
                    "hands": hands,
                    "objects": objects,
                    "dwells": interactions.progress(timestamp),
                }
                publish(client, args.api, {"event_type": "frame", **base})
                if recording_camera is not None:
                    recording_success, recording_frame = recording_camera.read()
                    if recording_success:
                        publish(
                            client,
                            args.api,
                            {
                                "event_type": "recording_frame",
                                "timestamp": timestamp,
                                "frame_image": encode_preview(
                                    recording_frame, args.preview_quality
                                ),
                            },
                        )
                for event in events:
                    publish(client, args.api, {**event, "hands": hands, "objects": objects})
                if args.preview:
                    draw_preview(frame, hands, objects)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                time.sleep(max(0.0, interval - (time.monotonic() - loop_started)))
        finally:
            camera.release()
            if recording_camera is not None:
                recording_camera.release()
            hand_tracker.close()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
