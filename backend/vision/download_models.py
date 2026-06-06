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
        return
    print(f"Downloading MediaPipe Hand Landmarker to {destination}")
    urllib.request.urlretrieve(HAND_LANDMARKER_URL, destination)


if __name__ == "__main__":
    main()
