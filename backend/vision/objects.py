from collections import defaultdict
from collections.abc import Callable


class ObjectDetector:
    """Detect registered memory objects with an open-vocabulary YOLO-World model."""

    def __init__(
        self,
        model_path: str = "yolov8m-worldv2.pt",
        confidence: float = 0.10,
        iou: float = 0.5,
        device: str | None = None,
        model_factory: Callable[[str], object] | None = None,
    ):
        if model_factory is None:
            from ultralytics import YOLOWorld

            model_factory = YOLOWorld
        self.model = model_factory(model_path)
        self.confidence = confidence
        self.iou = iou
        self.device = device
        self.registrations_by_prompt: dict[str, list[dict]] = {}

    def detect(self, frame, registrations: list[dict]) -> list[dict]:
        self.set_registrations(registrations)
        if not self.registrations_by_prompt:
            return []

        options = {
            "conf": self.confidence,
            "iou": self.iou,
            "verbose": False,
        }
        if self.device:
            options["device"] = self.device
        results = self.model.predict(frame, **options)
        if not results:
            return []
        return self._as_detections(results[0])

    def set_registrations(self, items: list[dict]) -> None:
        registrations: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            prompt = str(item["class_name"]).replace("_", " ").strip()
            if prompt:
                registrations[prompt].append(item)
        prompts = list(registrations)
        if prompts != list(self.registrations_by_prompt):
            if prompts:
                self.model.set_classes(prompts)
        self.registrations_by_prompt = dict(registrations)

    def _as_detections(self, result) -> list[dict]:
        height, width = result.orig_shape
        prompts = list(self.registrations_by_prompt)
        candidates: dict[int, list[tuple[float, list[float]]]] = defaultdict(list)
        for coordinates, confidence, class_index in zip(
            result.boxes.xyxy.tolist(),
            result.boxes.conf.tolist(),
            result.boxes.cls.tolist(),
            strict=True,
        ):
            candidates[int(class_index)].append((float(confidence), coordinates))

        detections = []
        for class_index, matches in candidates.items():
            if class_index >= len(prompts):
                continue
            prompt = prompts[class_index]
            registrations = self.registrations_by_prompt[prompt]
            matches.sort(key=lambda item: item[0], reverse=True)
            for registration, (confidence, coordinates) in zip(registrations, matches):
                x1, y1, x2, y2 = coordinates
                detections.append(
                    {
                        "object_id": registration["object_id"],
                        "class_name": registration["class_name"],
                        "confidence": confidence,
                        "bbox": {
                            "x1": max(0.0, min(1.0, x1 / width)),
                            "y1": max(0.0, min(1.0, y1 / height)),
                            "x2": max(0.0, min(1.0, x2 / width)),
                            "y2": max(0.0, min(1.0, y2 / height)),
                        },
                        "on_tray": True,
                    }
                )
        return detections
