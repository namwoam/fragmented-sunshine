import os
import urllib.request
from pathlib import Path

HAND_LANDMARKER_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)


def main() -> None:
    destination = Path(os.getenv("HAND_LANDMARKER_MODEL", "models/hand_landmarker.task"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        print(f"MediaPipe model already exists: {destination}")
    else:
        print(f"Downloading MediaPipe Hand Landmarker to {destination}")
        urllib.request.urlretrieve(HAND_LANDMARKER_URL, destination)

    from ultralytics import YOLOWorld

    object_model = os.getenv("YOLO_WORLD_MODEL", "yolov8m-worldv2.pt")
    print(f"Loading YOLO-World object detector and CLIP text encoder: {object_model}")
    detector = YOLOWorld(object_model)
    detector.set_classes(["object"])


if __name__ == "__main__":
    main()
