# Fragmented Sunshine of the Spotless Mind

A browser-based installation console and FastAPI media service for recording, segmenting, and randomly rearranging object-linked memories.

## Run locally

Prerequisites: Node.js, `uv`, Task, and optionally `ffmpeg` for physical video segment extraction.

```bash
task setup
task dev
```

Open `http://localhost:5173`. The API and its OpenAPI documentation run at `http://localhost:8000` and `http://localhost:8000/docs`.

The root `.env` is loaded by the backend. Supported settings are documented in `.env.example`; the existing `GEMINI_API_KEY` is used with Gemini 3.5 Flash-Lite for transcription and transcript segmentation.

## Commands

```bash
task setup           # install laptop application and camera-client dependencies
task dev             # run frontend, backend, and laptop camera inference client
task test            # lint, test, and build
task format          # format and autofix backend code
task backend:dev     # API only
task frontend:dev    # web client only
task vision:setup    # install vision dependencies and download hand/object models
task vision:client   # run only the laptop camera inference client
task vision:dev      # serve the remote MediaPipe + YOLO-World inference API
task vision:preview  # run the laptop client with a local preview window
task backend:test:unit         # CPU-only unit tests with mocked AI
task backend:test:integration  # API, SQLite, media, and WebSocket integration tests
```

## Continuous integration

GitHub Actions runs three independent jobs on pushes and pull requests:

- Backend unit tests and Ruff linting.
- Backend integration tests covering upload, mocked Gemini segmentation, persistence, playback, and vision WebSockets.
- Frontend ESLint and production TypeScript/Vite build.

CI installs only the standard backend development dependencies. MediaPipe, Ultralytics, model downloads, cameras, GPUs, and real API credentials are not required. Gemini responses are supplied by deterministic in-process fakes.

Open `http://localhost:5173/debug` to inspect live YOLO-World object detections, handedness, index fingertips, wrist movement vectors, and three-second activation events.
The tray camera defaults to device index `0`; the backend recording-camera debug feed defaults to index `1`. Override them with `TRAY_CAMERA_INDEX` and `RECORDING_CAMERA_INDEX`, or pass `--camera` and `--recording-camera` to `task vision:client --`. The client remembers each detected object box for 30 seconds so a touch can establish a hand lock after visual occlusion; tune this with `VISION_OBJECT_MEMORY_SECONDS` or `--object-memory-seconds`.

## Tray vision

The remote service uses MediaPipe Hand Landmarker for handedness, index-fingertip position, wrist movement, and speed, plus YOLOv8m-Worldv2 for open-vocabulary object detection. Each registered object's `class_name` becomes a visual prompt (underscores are converted to spaces). Holding the left index fingertip inside an object's live or recently remembered detection box for three seconds starts recording; moving it away stops recording. Holding the right fingertip there for three seconds starts playback. If camera mirroring reverses handedness, start the remote service with `task vision:dev -- --swap-handedness`.

The object detector defaults to `yolov8m-worldv2.pt`, confidence `0.10`, and IoU `0.5`. Override these with `YOLO_WORLD_MODEL`, `YOLO_WORLD_CONFIDENCE`, `YOLO_WORLD_IOU`, and `YOLO_WORLD_DEVICE`, or the matching `task vision:dev -- --object-*` flags. Model weights are downloaded by Ultralytics during `task vision:setup` and are not committed.

### Remote vision worker

`task dev` runs the API, frontend, and camera client on the laptop. For every tray frame, the client reads the current object catalog from the local API, sends a JPEG and those open-vocabulary prompts to the remote domain, receives hand and object detections in the same HTTP response, and publishes the results to the local API. Dwell tracking and the recording-camera debug feed remain on the laptop.

Only the remote inference domain needs to be reachable over the network. The remote server does not connect to the laptop, and the laptop does not expose its camera or local API. Configure the laptop's `.env` with the public HTTPS endpoint and a shared bearer token:

```dotenv
TRAY_CAMERA_INDEX=0
RECORDING_CAMERA_INDEX=1
VISION_INFERENCE_URL=https://vision.example.com
VISION_INFERENCE_TOKEN=replace-with-a-long-random-token
```

```bash
task setup
task dev
```

On the GPU server, clone the repository and configure the listener and the same token:

```dotenv
VISION_INFERENCE_HOST=0.0.0.0
VISION_INFERENCE_PORT=8010
VISION_INFERENCE_TOKEN=replace-with-a-long-random-token
YOLO_WORLD_DEVICE=0
```

Then run inference headlessly on the GPU server:

```bash
task vision:setup
task vision:dev
curl http://localhost:8010/health
```

Point the public domain's TLS reverse proxy at port `8010`; allow multipart request bodies large enough for a JPEG frame and use an upstream timeout longer than `VISION_INFERENCE_TIMEOUT_SECONDS`. The token is optional for local testing but strongly recommended for a public domain. Run `task vision:dev -- --help` and `task vision:client -- --help` for the Click-based server and client options.

## Docker

```bash
task docker:up
task docker:vision-models
```

The application is available at `http://localhost:8080`. The named `fragmented_sunshine_data` volume stores SQLite, recordings, transcripts, extracted segments, and MediaPipe model assets under `/data` in the backend container. `task docker:down` keeps the volume; `task docker:reset` explicitly deletes it.

`task docker:vision` starts the inference API in an existing backend container. Expose its configured inference port before using that setup. Laptop cameras remain attached to `task vision:client`, including on macOS where Docker Desktop does not expose webcams as `/dev/video*`.

## Current pipeline

1. The console seeds the three MVP objects and supports registration of additional YOLO-World visual class prompts.
2. A left-hand action records webcam and microphone media through the browser.
3. FastAPI stores media under `backend/data/objects/<object_id>/recordings/` and metadata in SQLite.
4. Processing reads a cached `transcript.json` or extracts 16 kHz mono audio with `ffmpeg` and sends it to the configured Gemini ASR model for verbatim, timestamped `zh-TW`/mixed-language transcription.
5. Gemini groups adjacent transcript units into validated semantic segments. Text-changing or unavailable model responses fall back to the original ASR units.
6. Exact H.264/AAC segment clips are extracted with `ffmpeg`; processing fails clearly instead of inventing placeholder transcripts when ASR is unavailable.
7. A right-hand action retrieves a freshly shuffled timeline by default. `POST /api/recordings/{recording_id}/timeline-renders` validates a complete segment permutation and renders it to one MP4.
8. `GET /api/recordings/{recording_id}/transcript` returns the persisted timestamped transcript, and rendered media is served from `/api/timeline-renders/{render_id}/media`.

The UI buttons are the demo interaction adapter. MediaPipe fingertip dwell events invoke the same recording and playback actions when the installation vision process is connected.

## API

The implementation includes object registration, multipart recording upload, processing, recording/media retrieval, playback timeline generation, and playback history endpoints described in the implementation plan.

Recordings can be preprocessed by placing this shape at the recording's `transcript.json` path before processing:

```json
{
  "language": "zh-TW",
  "segments": [
    { "start": 0.0, "end": 4.2, "text": "我看到這瓶香水的時候，還是會想到那一天。" }
  ]
}
```
