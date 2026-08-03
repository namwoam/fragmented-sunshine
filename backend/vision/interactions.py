from dataclasses import dataclass, field


def point_in_object(x: float, y: float, item: dict) -> bool:
    box = item["bbox"]
    return box["x1"] <= x <= box["x2"] and box["y1"] <= y <= box["y2"]


@dataclass
class DwellState:
    started_at: float
    fired: bool = False
    object_visible: bool = True


@dataclass
class ObjectMemory:
    item: dict
    seen_at: float


@dataclass
class InteractionStateManager:
    dwell_seconds: float = 3.0
    object_memory_seconds: float = 30.0
    states: dict[tuple[str, str], DwellState] = field(default_factory=dict)
    object_memories: dict[str, ObjectMemory] = field(default_factory=dict)

    def update(self, timestamp: float, hands: list[dict], objects: list[dict]) -> list[dict]:
        events = []
        active: set[tuple[str, str]] = set()

        hands_by_handedness = {hand["handedness"]: hand for hand in hands}
        objects_by_id = {
            item["object_id"]: item for item in objects if item.get("object_id") and "bbox" in item
        }
        for object_id, item in objects_by_id.items():
            self.object_memories[object_id] = ObjectMemory(
                item={"object_id": object_id, "bbox": dict(item["bbox"])},
                seen_at=timestamp,
            )
        for object_id, memory in list(self.object_memories.items()):
            if timestamp - memory.seen_at > self.object_memory_seconds:
                self.object_memories.pop(object_id)

        # A live hand/object overlap establishes a trusted identity lock. Once
        # established, retain it while the same hand remains visible even if the
        # hand occludes the object detector. A live object detection outside the
        # fingertip, or loss of the hand, is explicit evidence that contact ended.
        for key, state in self.states.items():
            object_id, handedness = key
            hand = hands_by_handedness.get(handedness)
            if hand is None:
                continue
            item = objects_by_id.get(object_id)
            if item is not None and not point_in_object(hand["touch_x"], hand["touch_y"], item):
                continue
            state.object_visible = item is not None
            active.add(key)
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

        candidates = [(item, True) for item in objects_by_id.values()]
        candidates.extend(
            (memory.item, False)
            for object_id, memory in sorted(
                self.object_memories.items(), key=lambda entry: entry[1].seen_at, reverse=True
            )
            if object_id not in objects_by_id
        )

        locked_hands = {handedness for _, handedness in active}
        for item, object_visible in candidates:
            object_id = item["object_id"]
            for hand in hands:
                handedness = hand["handedness"]
                key = (object_id, handedness)
                if not point_in_object(hand["touch_x"], hand["touch_y"], item):
                    continue
                active.add(key)
                if key in self.states:
                    continue
                if handedness in locked_hands:
                    active.discard(key)
                    continue
                self.states[key] = DwellState(timestamp, object_visible=object_visible)
                locked_hands.add(handedness)

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

    def locks(self) -> list[dict]:
        return [
            {
                "object_id": object_id,
                "handedness": handedness,
                "status": (
                    "activated"
                    if state.fired
                    else "live"
                    if state.object_visible
                    else "hand_locked"
                ),
                "object_visible": state.object_visible,
            }
            for (object_id, handedness), state in self.states.items()
        ]

    def progress(self, timestamp: float) -> list[dict]:
        return [
            {
                "object_id": object_id,
                "handedness": handedness,
                "elapsed_seconds": min(timestamp - state.started_at, self.dwell_seconds),
                "remaining_seconds": max(0.0, self.dwell_seconds - (timestamp - state.started_at)),
                "progress": min(1.0, max(0.0, (timestamp - state.started_at) / self.dwell_seconds)),
            }
            for (object_id, handedness), state in self.states.items()
            if not state.fired
        ]
