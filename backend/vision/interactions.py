from dataclasses import dataclass, field


def intersection_ratio(first: dict, second: dict) -> float:
    left = max(first["x1"], second["x1"])
    top = max(first["y1"], second["y1"])
    right = min(first["x2"], second["x2"])
    bottom = min(first["y2"], second["y2"])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.001, (first["x2"] - first["x1"]) * (first["y2"] - first["y1"]))
    return intersection / first_area


def center_in_roi(box: dict, roi: tuple[float, float, float, float]) -> bool:
    center_x = (box["x1"] + box["x2"]) / 2
    center_y = (box["y1"] + box["y2"]) / 2
    return roi[0] <= center_x <= roi[2] and roi[1] <= center_y <= roi[3]


@dataclass
class TrackedState:
    stable: str | None = None
    candidate: str | None = None
    candidate_since: float = 0.0


@dataclass
class InteractionStateManager:
    debounce_seconds: float = 0.4
    overlap_threshold: float = 0.12
    tray_roi: tuple[float, float, float, float] = (0.08, 0.08, 0.92, 0.92)
    states: dict[str, TrackedState] = field(default_factory=dict)

    def update(self, timestamp: float, hands: list[dict], objects: list[dict]) -> list[dict]:
        events = []
        visible_ids = {item["object_id"] for item in objects if item.get("object_id")}
        known_ids = visible_ids | set(self.states)
        by_id = {item["object_id"]: item for item in objects if item.get("object_id")}

        for object_id in known_ids:
            item = by_id.get(object_id)
            raw_state = self._classify(item, hands)
            tracked = self.states.setdefault(object_id, TrackedState())
            if raw_state != tracked.candidate:
                tracked.candidate = raw_state
                tracked.candidate_since = timestamp
                continue
            if (
                raw_state == tracked.stable
                or timestamp - tracked.candidate_since < self.debounce_seconds
            ):
                continue

            previous = tracked.stable
            tracked.stable = raw_state
            if previous == "on_tray" and raw_state.startswith("held_"):
                events.append(
                    self._event(
                        "object_lifted", timestamp, object_id, raw_state.removeprefix("held_")
                    )
                )
            elif previous and previous.startswith("held_") and raw_state == "on_tray":
                events.append(
                    self._event(
                        "object_returned", timestamp, object_id, previous.removeprefix("held_")
                    )
                )
        return events

    def _classify(self, item: dict | None, hands: list[dict]) -> str:
        if item is None:
            return "absent"
        overlaps = [
            (intersection_ratio(item["bbox"], hand["bbox"]), hand["handedness"]) for hand in hands
        ]
        if overlaps:
            ratio, handedness = max(overlaps)
            if ratio >= self.overlap_threshold:
                return f"held_{handedness}"
        return "on_tray" if center_in_roi(item["bbox"], self.tray_roi) else "outside_tray"

    @staticmethod
    def _event(event_type: str, timestamp: float, object_id: str, handedness: str) -> dict:
        return {
            "event_type": event_type,
            "timestamp": timestamp,
            "object_id": object_id,
            "handedness": handedness,
        }
