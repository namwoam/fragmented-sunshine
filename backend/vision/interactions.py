from dataclasses import dataclass, field


def point_in_location(x: float, y: float, location: dict) -> bool:
    distance = ((x - location["location_x"]) ** 2 + (y - location["location_y"]) ** 2) ** 0.5
    return distance <= location.get("touch_radius", 0.08)


@dataclass
class DwellState:
    started_at: float
    fired: bool = False


@dataclass
class InteractionStateManager:
    dwell_seconds: float = 3.0
    states: dict[tuple[str, str], DwellState] = field(default_factory=dict)

    def update(self, timestamp: float, hands: list[dict], objects: list[dict]) -> list[dict]:
        events = []
        active: set[tuple[str, str]] = set()

        for item in objects:
            object_id = item.get("object_id")
            if not object_id or item.get("location_x") is None or item.get("location_y") is None:
                continue
            for hand in hands:
                handedness = hand["handedness"]
                key = (object_id, handedness)
                if not point_in_location(hand["touch_x"], hand["touch_y"], item):
                    continue
                active.add(key)
                state = self.states.setdefault(key, DwellState(timestamp))
                if not state.fired and timestamp - state.started_at >= self.dwell_seconds:
                    state.fired = True
                    events.append(
                        {
                            "event_type": "object_activated",
                            "timestamp": timestamp,
                            "object_id": object_id,
                            "handedness": handedness,
                        }
                    )

        for key in set(self.states) - active:
            state = self.states.pop(key)
            if state.fired:
                object_id, handedness = key
                events.append(
                    {
                        "event_type": "object_released",
                        "timestamp": timestamp,
                        "object_id": object_id,
                        "handedness": handedness,
                    }
                )
        return events

    def progress(self, timestamp: float) -> list[dict]:
        return [
            {
                "object_id": object_id,
                "handedness": handedness,
                "elapsed_seconds": min(timestamp - state.started_at, self.dwell_seconds),
                "remaining_seconds": max(
                    0.0, self.dwell_seconds - (timestamp - state.started_at)
                ),
                "progress": min(
                    1.0, max(0.0, (timestamp - state.started_at) / self.dwell_seconds)
                ),
            }
            for (object_id, handedness), state in self.states.items()
            if not state.fired
        ]
