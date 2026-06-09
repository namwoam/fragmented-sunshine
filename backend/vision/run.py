import argparse
import base64
import json
import os
import time
from pathlib import Path

import cv2
import httpx
import mediapipe as mp
from ultralytics import YOLO

from .interactions import InteractionStateManager, center_in_roi


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tray hand and object vision service")
    parser.add_argument("--camera", type=int, default=int(os.getenv("TRAY_CAMERA_INDEX", "0")))
    parser.add_argument("--api", default=os.getenv("VISION_API_URL", "http://localhost:8000"))
    parser.add_argument("--yolo-model", default=os.getenv("YOLO_MODEL", "yolo11n.pt"))
    parser.add_argument(
        "--hand-model",
        default=os.getenv("HAND_LANDMARKER_MODEL", "models/hand_landmarker.task"),
    )
    parser.add_argument("--object-map", default=os.getenv("VISION_OBJECT_MAP", "{}"))
    parser.add_argument("--confidence", type=float, default=0.45)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--preview-quality", type=int, default=65)
    parser.add_argument("--debounce-ms", type=int, default=400)
    parser.add_argument("--tray-roi", default=os.getenv("TRAY_ROI", "0.08,0.08,0.92,0.92"))
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
                }
            )
        return hands

    def close(self) -> None:
        self.landmarker.close()


class ObjectTracker:
    def __init__(self, model_path: str, object_map: dict[str, str], confidence: float):
        self.model = YOLO(model_path)
        self.object_map = {key.lower(): value for key, value in object_map.items()}
        self.confidence = confidence

    def detect(self, frame, tray_roi: tuple[float, float, float, float]) -> list[dict]:
        height, width = frame.shape[:2]
        result = self.model.predict(frame, conf=self.confidence, verbose=False)[0]
        detections = []
        for box in result.boxes:
            class_name = result.names[int(box.cls.item())]
            coordinates = box.xyxy[0].tolist()
            bbox = {
                "x1": coordinates[0] / width,
                "y1": coordinates[1] / height,
                "x2": coordinates[2] / width,
                "y2": coordinates[3] / height,
            }
            object_id = self.object_map.get(class_name.lower())
            if object_id is None and class_name.lower() in self.object_map.values():
                object_id = class_name.lower()
            detections.append(
                {
                    "object_id": object_id,
                    "class_name": class_name,
                    "confidence": float(box.conf.item()),
                    "bbox": bbox,
                    "on_tray": center_in_roi(bbox, tray_roi),
                }
            )
        return detections


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


def draw_preview(frame, hands: list[dict], objects: list[dict], roi) -> None:
    height, width = frame.shape[:2]
    cv2.rectangle(
        frame,
        (int(roi[0] * width), int(roi[1] * height)),
        (int(roi[2] * width), int(roi[3] * height)),
        (180, 180, 180),
        1,
    )
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
    cv2.imshow("Fragmented Sunshine - Tray Vision", frame)


def main() -> None:
    args = parse_args()
    hand_model = Path(args.hand_model)
    if not hand_model.exists():
        raise SystemExit(f"MediaPipe model not found: {hand_model}. Run `task vision:models`.")
    object_map = json.loads(args.object_map or "{}")
    tray_roi = tuple(float(value) for value in args.tray_roi.split(","))
    if len(tray_roi) != 4:
        raise SystemExit("--tray-roi must contain x1,y1,x2,y2")

    hand_tracker = HandTracker(str(hand_model), args.swap_handedness)
    object_tracker = ObjectTracker(args.yolo_model, object_map, args.confidence)
    interactions = InteractionStateManager(args.debounce_ms / 1000, tray_roi=tray_roi)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        raise SystemExit(f"Could not open tray camera {args.camera}")

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
                objects = object_tracker.detect(frame, tray_roi)
                base = {
                    "timestamp": timestamp,
                    "frame_image": encode_preview(frame, args.preview_quality),
                    "hands": hands,
                    "objects": objects,
                }
                publish(client, args.api, {"event_type": "frame", **base})
                for event in interactions.update(timestamp, hands, objects):
                    publish(client, args.api, {**event, "hands": hands, "objects": objects})
                if args.preview:
                    draw_preview(frame, hands, objects, tray_roi)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                time.sleep(max(0.0, interval - (time.monotonic() - loop_started)))
        finally:
            camera.release()
            hand_tracker.close()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
