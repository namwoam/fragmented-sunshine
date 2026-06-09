# Fragmented Sunshine of the Spotless Mind

A browser-based installation console and FastAPI media service for recording, segmenting, and progressively rearranging object-linked memories.

## Run locally

Prerequisites: Node.js, `uv`, Task, and optionally `ffmpeg` for physical video segment extraction.

```bash
task setup
task dev
```

Open `http://localhost:5173`. The API and its OpenAPI documentation run at `http://localhost:8000` and `http://localhost:8000/docs`.

The root `.env` is loaded by the backend. Supported settings are documented in `.env.example`; the existing `GEMINI_API_KEY` is used for transcript segmentation.

## Commands

```bash
task setup           # install all dependencies
task dev             # run frontend and backend concurrently
task test            # lint, test, and build
task format          # format and autofix backend code
task backend:dev     # API only
task frontend:dev    # web client only
task vision:setup    # install MediaPipe/OpenCV and download hand model
task vision:dev      # run tray-camera inference with a preview window
task backend:test:unit         # CPU-only unit tests with mocked AI
task backend:test:integration  # API, SQLite, media, and WebSocket integration tests
```

## Continuous integration

GitHub Actions runs three independent jobs on pushes and pull requests:

- Backend unit tests and Ruff linting.
- Backend integration tests covering upload, mocked Gemini segmentation, persistence, playback, and vision WebSockets.
- Frontend ESLint and production TypeScript/Vite build.

CI installs only the standard backend development dependencies. MediaPipe, Ultralytics, model downloads, cameras, GPUs, and real API credentials are not required. Gemini responses are supplied by deterministic in-process fakes.

Open `http://localhost:5173/debug` to inspect registered object locations, handedness, index fingertips, wrist movement vectors, and three-second activation events.
The tray camera defaults to device index `0`; the backend recording-camera debug feed defaults to index `1`. Override them with `TRAY_CAMERA_INDEX` and `RECORDING_CAMERA_INDEX`, or pass `--camera` and `--recording-camera` to `task vision:dev --`.

## Tray vision

The tray worker uses MediaPipe Hand Landmarker for handedness, index-fingertip position, wrist movement, and speed. Select an object in the installation console, choose **Set selected location**, and click its fixed position in the live tray image. Holding the left index fingertip in that region for three seconds starts recording; moving it away stops recording. Holding the right fingertip there for three seconds starts playback. If camera mirroring reverses handedness, start the worker with `task vision:dev -- --swap-handedness`.

## Docker

```bash
task docker:up
task docker:vision-models
```

The application is available at `http://localhost:8080`. The named `fragmented_sunshine_data` volume stores SQLite, recordings, transcripts, extracted segments, and MediaPipe model assets under `/data` in the backend container. `task docker:down` keeps the volume; `task docker:reset` explicitly deletes it.

On a Linux installation host, pass the tray camera into the backend container and run `task docker:vision`. Docker Desktop on macOS does not expose webcams as `/dev/video*`, so run `task vision:dev` on the host while the two application containers are running; it publishes detections to port 8080 through the frontend proxy.

## Current pipeline

1. The console seeds the three MVP objects and supports registration of additional objects.
2. A left-hand action records webcam and microphone media through the browser.
3. FastAPI stores media under `backend/data/objects/<object_id>/recordings/` and metadata in SQLite.
4. Processing reads a timestamped `transcript.json` when supplied. Until Breeze-ASR is deployed, it creates neutral placeholder timestamp units.
5. Gemini converts timestamped transcripts into structured reorderable segments. Network or model failures use the input units unchanged.
6. A right-hand action retrieves a deterministic timeline whose disruption increases with replay count.
7. With `ffmpeg`, physical clips are extracted. Without it, the browser plays the same timeline by seeking through the original media.

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
