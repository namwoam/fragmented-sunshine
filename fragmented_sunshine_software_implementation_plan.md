# Software Implementation Plan
## Fragmented Sunshine of the Spotless Mind

## 1. Purpose

This document outlines the software implementation plan for **Fragmented Sunshine of the Spotless Mind**, an interactive installation that supports gradual forgetting through tactile interaction with memory-linked objects.

The system should:

1. Detect which object is being handled on the tray.
2. Detect whether the object is picked up with the left or right hand.
3. Record video and audio when an object is picked up with the left hand.
4. Replay the associated audiovisual memory when the same object is picked up with the right hand.
5. Transcribe recorded speech into timestamped segments.
6. Re-edit each playback timeline by randomly rearranging recognizable speech segments.

The system does **not** delete recordings immediately. Instead, it changes the temporal order of recorded speech while preserving recognizable fragments.

---

## 2. System Overview

### 2.1 Hardware Inputs

| Component | Purpose |
|---|---|
| Tray-facing webcam | Detects hands and identifies objects placed on or lifted from the tray |
| User-facing webcam | Records the user's video reflection |
| Microphone | Captures the user's spoken reflection |
| Computer display | Shows recording status and replays stored memories |
| Remote server | Runs inference services and stores recordings, transcripts, segments, and replay histories |

### 2.2 Core Interaction Logic

| User action | System response |
|---|---|
| Place an object on the tray | Detect and register the object |
| Pick up an object with the left hand | Start simultaneous video and audio recording |
| Return the object to the tray | Stop recording and upload the media |
| Pick up an object with the right hand | Retrieve and replay the associated recording |
| Repeated right-hand retrievals | Replay a freshly shuffled timeline |

---

## 3. High-Level Architecture

```text
Tray-facing Webcam
        |
        v
Hand Tracking + Object Detection
        |
        v
Interaction State Manager
   |                  |
   | left hand        | right hand
   v                  v
Recording Service     Playback Service
   |                  |
   v                  v
Remote Server <---- Media Database
   |
   +--> ASR Transcription
   |
   +--> Transcript Segmentation
   |
   +--> Timeline Re-editing
```

---

## 4. Client Application

The client application runs on the installation computer and coordinates camera input, interaction states, recording, playback, and server communication.

### 4.1 Tray Vision Module

**Goal:** Detect hand position, handedness, and the active object.

**Recommended components:**

- **MediaPipe Hand Landmarker** for hand landmarks and handedness classification.
- **YOLO11** for object detection.

**Inputs:**

- Frames from the tray-facing webcam.

**Outputs:**

```json
{
  "timestamp": 1720000000.0,
  "hands": [
    {
      "handedness": "left",
      "confidence": 0.97,
      "bbox": [120, 80, 260, 310]
    }
  ],
  "objects": [
    {
      "object_id": "perfume_01",
      "class_name": "perfume_bottle",
      "confidence": 0.94,
      "bbox": [180, 160, 240, 280]
    }
  ]
}
```

### 4.2 Interaction State Manager

**Goal:** Convert continuous visual detections into stable interaction events.

Each object should have one of the following states:

```text
ON_TRAY
LIFTED_BY_LEFT_HAND
LIFTED_BY_RIGHT_HAND
RECORDING
PLAYING
PROCESSING
```

**Debouncing rule:** Require stable hand-object overlap for a short duration, such as 300–500 ms, before triggering an event.

**Example transition:**

```text
ON_TRAY
  -> LIFTED_BY_LEFT_HAND
  -> RECORDING
  -> ON_TRAY
  -> PROCESSING
```

### 4.3 Recording Module

**Trigger:** An object is picked up with the left hand.

**Behavior:**

1. Start the user-facing webcam.
2. Start microphone capture.
3. Show a simple recording indicator on the display.
4. Stop recording when the object returns to the tray or after a configured timeout.
5. Upload the media file and metadata to the server.

**Stored metadata:**

```json
{
  "object_id": "perfume_01",
  "recording_id": "rec_2026_06_06_001",
  "started_at": "2026-06-06T14:00:00+08:00",
  "ended_at": "2026-06-06T14:01:05+08:00",
  "duration_seconds": 65,
  "source": "left_hand_interaction"
}
```

### 4.4 Playback Module

**Trigger:** An object is picked up with the right hand.

**Behavior:**

1. Request the latest replay timeline for the active object.
2. Retrieve the corresponding video segments.
3. Assemble or stream the re-edited playback sequence.
4. Play the result on the installation display.
5. Increment the replay count.
6. Save the replay history.

---

## 5. Server-Side Processing Pipeline

### 5.1 Media Upload and Storage

Store:

- Original video.
- Original audio.
- Timestamped transcript.
- Transcript segments.
- Re-edited replay timelines.
- Object-to-recording associations.
- Replay count and playback history.

**Suggested directory structure:**

```text
data/
  objects/
    perfume_01/
      recordings/
        rec_2026_06_06_001/
          original.mp4
          audio.wav
          transcript.json
          segments.json
          timelines.json
```

### 5.2 Speech-to-Text Service

Use **MediaTek Breeze-ASR-25** to transcribe recorded reflections.

**Reason for selection:** The installation is designed for users in Taiwan, and the model is appropriate for Taiwanese Mandarin and mixed Mandarin-English speech.

**Required output format:**

```json
{
  "language": "zh-TW",
  "segments": [
    {
      "start": 0.0,
      "end": 4.2,
      "text": "我看到這瓶香水的時候，還是會想到那一天。"
    },
    {
      "start": 4.2,
      "end": 8.7,
      "text": "那是我們第一次一起旅行。"
    }
  ]
}
```

### 5.3 Transcript Segmentation Service

Use a configurable LLM endpoint, with **Gemini 3.5 Flash** as the initial target model.

**Goal:** Divide the transcript into semantically meaningful, reorderable segments.

**Constraints:**

- Preserve the original wording.
- Preserve timestamp ranges.
- Avoid splitting inside a sentence unless necessary.
- Return a valid JSON structure.
- Do not invent new content.
- Keep segments short enough to be rearranged during playback.

**Example prompt requirement:**

```text
Segment the transcript into reorderable spoken units.
Preserve the original words and timestamps.
Do not summarize, rewrite, or add content.
Return JSON only.
```

**Expected output:**

```json
{
  "segments": [
    {
      "segment_id": "seg_01",
      "start": 0.0,
      "end": 4.2,
      "text": "我看到這瓶香水的時候，還是會想到那一天。"
    },
    {
      "segment_id": "seg_02",
      "start": 4.2,
      "end": 8.7,
      "text": "那是我們第一次一起旅行。"
    }
  ]
}
```

### 5.4 Video Segment Extraction

Use `ffmpeg` to cut the original recording according to timestamped transcript segments.

**Example command:**

```bash
ffmpeg -i original.mp4 -ss 0.0 -to 4.2 -c copy seg_01.mp4
```

For more reliable cutting, re-encode the output if keyframe alignment causes visible errors.

### 5.5 Timeline Re-editing Strategy

The system should preserve recognizable speech fragments while randomly shuffling their order for each playback request.

**Example playback:**

```text
3 -> 1 -> 4 -> 2
```

**Another playback:**

```text
2 -> 4 -> 1 -> 3
```

The re-editing function should produce a fresh full permutation for each playback request.

```python
def reorder_segments(segment_ids):
    """
    Return a randomly shuffled segment order while preserving every segment.
    Avoid returning the original order when multiple segments are available.
    """
```

Shuffle once when a playback timeline is requested, not on every video frame. Keep every segment exactly once and avoid aggressive visual distortion. The intended effect is temporal rearrangement, not visual noise.

---

## 6. Suggested API Endpoints

### Register an object

```http
POST /api/objects
```

```json
{
  "object_id": "perfume_01",
  "class_name": "perfume_bottle",
  "display_name": "Small perfume bottle"
}
```

### Upload a recording

```http
POST /api/recordings
```

Multipart payload:

```text
object_id
video_file
audio_file
started_at
ended_at
```

### Process a recording

```http
POST /api/recordings/{recording_id}/process
```

### Retrieve a playback timeline

```http
GET /api/objects/{object_id}/playback
```

Example response:

```json
{
  "object_id": "perfume_01",
  "recording_id": "rec_2026_06_06_001",
  "replay_count": 3,
  "timeline": [
    "seg_01",
    "seg_03",
    "seg_02",
    "seg_04"
  ]
}
```

### Save playback history

```http
POST /api/objects/{object_id}/playback-events
```

```json
{
  "recording_id": "rec_2026_06_06_001",
  "timeline": ["seg_01", "seg_03", "seg_02", "seg_04"],
  "played_at": "2026-06-06T14:10:00+08:00"
}
```

---

## 7. Data Model

### Object

```text
object_id
class_name
display_name
created_at
```

### Recording

```text
recording_id
object_id
video_path
audio_path
duration_seconds
created_at
processing_status
```

### Segment

```text
segment_id
recording_id
start_time
end_time
transcript_text
video_segment_path
```

### Playback Event

```text
playback_event_id
recording_id
object_id
replay_count
timeline_order
played_at
```

---

## 8. Development Milestones

### Phase 1 — Basic Interaction Prototype

- Connect both webcams and microphone.
- Detect left and right hands using MediaPipe.
- Detect tray objects using YOLO11.
- Trigger recording and replay with hand-object interactions.
- Play the original recording without re-editing.

### Phase 2 — Remote Processing

- Add media upload.
- Add persistent storage.
- Integrate Breeze-ASR-25.
- Store timestamped transcripts.
- Verify Traditional Chinese transcript quality.

### Phase 3 — Timeline Re-editing

- Integrate Gemini-based transcript segmentation.
- Extract reusable video segments.
- Implement progressive timeline rearrangement.
- Render and replay reordered sequences.

### Phase 4 — Installation Hardening

- Add retry logic for unstable network connections.
- Add local caching when the remote server is unavailable.
- Tune hand-object interaction thresholds.
- Add object registration and calibration tools.
- Test with plush toys, handwritten cards, and small perfume bottles.

---

## 9. Testing Plan

### 9.1 Functional Tests

| Test | Expected result |
|---|---|
| Left hand lifts registered object | Recording starts |
| Object returns to tray | Recording stops and uploads |
| Right hand lifts registered object | Playback begins |
| Same object is replayed multiple times | A fresh shuffled timeline is returned |
| User speaks Mandarin with English words | Transcript preserves mixed-language speech |
| Server temporarily disconnects | Client caches media and retries upload |

### 9.2 Interaction Tests

Measure:

- False triggers caused by hands entering the camera frame.
- Accuracy of left/right hand classification.
- Accuracy of object recognition for visually similar items.
- Latency between object pickup and recording or playback.
- Whether users understand the two-handed interaction without explanation.
- Whether reordered timelines remain recognizable but harder to reconstruct.

### 9.3 Privacy and Data Handling

Because recordings may contain emotionally sensitive material:

- Store recordings securely.
- Restrict server access.
- Avoid sending unnecessary personal data to third-party services.
- Provide a local deletion mechanism.
- Clearly inform participants how recordings are processed and stored.
- Use synthetic or staged recordings during public exhibitions unless participants explicitly consent.

---

## 10. Recommended Technology Stack

| Layer | Suggested technology |
|---|---|
| Client application | Python or Electron |
| Computer vision | MediaPipe Hand Landmarker, Ultralytics YOLO11 |
| Media capture | OpenCV, WebRTC, or browser MediaRecorder |
| Video processing | `ffmpeg` |
| Backend API | FastAPI |
| Storage | Local filesystem or object storage with SQLite/PostgreSQL metadata |
| ASR | MediaTek Breeze-ASR-25 |
| Transcript segmentation | Gemini 3.5 Flash through a configurable LLM service |
| Playback | HTML5 video, VLC bindings, or a lightweight desktop media player |

---

## 11. Open Questions

- Should each object store only one reflection or a history of reflections?
- How should shuffle intensity affect recognizability?
- Should users be able to recover the original recording?
- How should the installation handle multiple similar objects?
- Which parts of the pipeline must remain local for privacy-sensitive deployments?

---

## 12. Minimum Viable Demo

For a short paper demonstration, the minimum viable system should support:

1. Three registered objects: a plush toy, a handwritten card, and a perfume bottle.
2. Stable left-hand recording and right-hand replay.
3. Concurrent video and audio capture.
4. Timestamped Traditional Chinese transcription.
5. Sentence-level segmentation.
6. Fresh randomized timelines across repeated playback requests.
7. A local fallback mode using preprocessed recordings if the remote server is unavailable.
