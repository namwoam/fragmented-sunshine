import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { PlaybackPlayer } from './components/PlaybackPlayer'
import { ObjectRegistration } from './components/ObjectRegistration'
import { useRecorder } from './hooks/useRecorder'
import { useVisionEvents } from './hooks/useVisionEvents'
import { cacheRecording, retryCachedRecordings } from './offline'
import type { InteractionState, MemoryObject, Playback, VisionEvent } from './types'
import './styles.css'

const stateCopy: Record<InteractionState, { label: string; detail: string }> = {
  on_tray: { label: 'Waiting', detail: 'Touch a detected object for three seconds with either hand.' },
  recording: { label: 'Remembering', detail: 'Keep touching the detected object. Move your left hand away to finish.' },
  processing: { label: 'Settling', detail: 'The memory is being divided into fragments.' },
  playing: { label: 'Reappearing', detail: 'A familiar memory returns in a changed order.' },
  unavailable: { label: 'Offline', detail: 'The server could not be reached. Your recording remains in this browser.' },
}

export default function App() {
  const [objects, setObjects] = useState<MemoryObject[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [state, setState] = useState<InteractionState>('on_tray')
  const [playback, setPlayback] = useState<Playback | null>(null)
  const [message, setMessage] = useState('')
  const startedAt = useRef<Date | null>(null)
  const recordingObjectId = useRef('')
  const stateRef = useRef<InteractionState>('on_tray')
  const { previewRef, start, stop } = useRecorder()

  useEffect(() => {
    stateRef.current = state
  }, [state])

  useEffect(() => {
    api.objects()
      .then((items) => {
        setObjects(items)
        setSelectedId(items[0]?.object_id ?? '')
        void retryCachedRecordings(async (cached) => {
          const formData = new FormData()
          formData.set('object_id', cached.objectId)
          formData.set('started_at', cached.startedAt)
          formData.set('ended_at', cached.endedAt)
          formData.set('video_file', cached.blob, 'reflection.webm')
          const result = await api.uploadRecording(formData)
          await api.processRecording(result.recording_id)
        }).then((count) => {
          if (count) setMessage(`${count} locally cached recording${count === 1 ? '' : 's'} uploaded.`)
        })
      })
      .catch(() => setState('unavailable'))
  }, [])

  async function startRecording(objectId = selectedId) {
    if (!objectId) return
    try {
      await start()
      setSelectedId(objectId)
      recordingObjectId.current = objectId
      startedAt.current = new Date()
      setMessage('')
      setState('recording')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'Camera and microphone are unavailable')
    }
  }

  async function finishRecording() {
    let blob: Blob | null = null
    const endedAt = new Date()
    try {
      blob = await stop()
      const formData = new FormData()
      formData.set('object_id', recordingObjectId.current)
      formData.set('started_at', (startedAt.current ?? endedAt).toISOString())
      formData.set('ended_at', endedAt.toISOString())
      formData.set('video_file', blob, 'reflection.webm')
      setState('processing')
      const result = await api.uploadRecording(formData)
      await api.processRecording(result.recording_id)
      setState('on_tray')
      setMessage('Memory stored. It can now be recalled.')
    } catch (reason) {
      if (blob) {
        await cacheRecording({
          objectId: recordingObjectId.current,
          startedAt: (startedAt.current ?? endedAt).toISOString(),
          endedAt: endedAt.toISOString(),
          blob,
        })
      }
      setState('unavailable')
      const detail = reason instanceof Error ? reason.message : 'Upload failed'
      setMessage(`${detail}. The recording was saved locally for retry.`)
    }
  }

  async function beginPlayback(objectId = selectedId) {
    if (!objectId) return
    try {
      setSelectedId(objectId)
      const nextPlayback = await api.playback(objectId)
      setPlayback(nextPlayback)
      setState('playing')
      setMessage('')
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : 'No memory is ready for this object')
    }
  }

  const finishPlayback = useCallback(() => {
    const completedPlayback = playback
    setPlayback(null)
    setState('on_tray')
    if (completedPlayback) void api.savePlayback(completedPlayback).catch(() => undefined)
  }, [playback])

  function handleVisionEvent(event: VisionEvent) {
    if (event.event_type === 'frame') {
      const activeDwell = event.dwells?.reduce((current, dwell) =>
        !current || dwell.progress > current.progress ? dwell : current, event.dwells[0])
      if (activeDwell) setSelectedId(activeDwell.object_id)
      return
    }
    if (!event.object_id) return
    if (event.event_type === 'object_activated' && stateRef.current === 'on_tray') {
      if (event.handedness === 'left') void startRecording(event.object_id)
      if (event.handedness === 'right') void beginPlayback(event.object_id)
    }
    if (
      event.event_type === 'object_released'
      && event.handedness === 'left'
      && stateRef.current === 'recording'
      && event.object_id === recordingObjectId.current
    ) {
      void finishRecording()
    }
  }

  const vision = useVisionEvents(handleVisionEvent)

  const selected = objects.find((object) => object.object_id === selectedId)
  const status = stateCopy[state]
  const activeDwells = vision.lastFrame?.dwells ?? []

  return (
    <main>
      <header>
        <p className="eyebrow">Interactive memory archive</p>
        <h1>
          <span>Fragmented Sunshine</span>
          <span>of the Spotless Mind</span>
        </h1>
        <p className="clock">{new Date().getFullYear()} / Installation console</p>
      </header>

      <section className="workspace">
        <aside>
          <div className="section-heading"><span>01</span><h2>Object</h2></div>
          <div className="object-list">
            {objects.map((object, index) => {
              const objectDwells = activeDwells.filter((dwell) => dwell.object_id === object.object_id)
              return (
                <div
                  key={object.object_id}
                  className={`${selectedId === object.object_id ? 'object-card active' : 'object-card'}${objectDwells.length ? ' dwelling' : ''}`}
                >
                  <button
                    className="object"
                    onClick={() => setSelectedId(object.object_id)}
                    disabled={state !== 'on_tray'}
                  >
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{object.display_name}</strong>
                    <small>{object.class_name.replaceAll('_', ' ')}</small>
                    <small className="location-status">YOLO-World detection enabled</small>
                    {objectDwells.map((dwell) => (
                      <span className={`object-progress ${dwell.handedness}`} key={dwell.handedness}>
                        <span className="object-progress-copy">
                          <small>{dwell.handedness} / {dwell.handedness === 'left' ? 'record' : 'playback'}</small>
                          <strong>{dwell.remaining_seconds.toFixed(1)}s</strong>
                        </span>
                        <span className="object-progress-track" aria-hidden="true">
                          <span style={{ width: `${dwell.progress * 100}%` }} />
                        </span>
                      </span>
                    ))}
                  </button>
                </div>
              )
            })}
          </div>
          <ObjectRegistration
            onSaved={(object) => {
              setObjects((items) => items.some((item) => item.object_id === object.object_id)
                ? items.map((item) => item.object_id === object.object_id ? object : item)
                : [...items, object])
              setSelectedId(object.object_id)
            }}
          />
        </aside>

        <section className="stage">
          <div className={`status-orbit ${state}`}>
            <span className="pulse" />
            <div><small>System state</small><strong>{status.label}</strong></div>
          </div>

          {state === 'playing' && playback ? (
            <PlaybackPlayer
              key={`${playback.recording_id}-${playback.replay_count}`}
              playback={playback}
              onComplete={finishPlayback}
            />
          ) : (
            <video
              className={state === 'recording' ? 'preview visible' : 'preview'}
              ref={previewRef}
              autoPlay
              muted
              playsInline
            />
          )}

          <div className="stage-copy">
            <p>{status.detail}</p>
            {selected && <span>Active object / {selected.display_name}</span>}
            {message && <span className="message">{message}</span>}
          </div>
        </section>

        <aside className="controls">
          <div className="section-heading"><span>02</span><h2>Gesture</h2></div>
          <button className="gesture left" onClick={() => void (state === 'recording' ? finishRecording() : startRecording())} disabled={!selectedId || !['on_tray', 'recording'].includes(state)}>
            <span className="hand">L</span>
            <span><strong>{state === 'recording' ? 'Move hand away' : 'Left touch / 3 sec'}</strong><small>{state === 'recording' ? 'Finish recording' : 'Record a memory'}</small></span>
          </button>
          <button className="gesture right" onClick={() => void beginPlayback()} disabled={!selectedId || state !== 'on_tray'}>
            <span className="hand">R</span>
            <span><strong>Right touch / 3 sec</strong><small>Recall a memory</small></span>
          </button>
          <div className="vision-readout">
            <span className={vision.connected ? 'vision-dot connected' : 'vision-dot'} />
            <div>
              <strong>Tray vision {vision.connected ? 'connected' : 'waiting'}</strong>
              <small>
                {vision.lastFrame
                  ? `${vision.lastFrame.hands.length} hands / ${vision.lastFrame.objects.length} objects`
                  : 'No frames received'}
              </small>
            </div>
          </div>
          <p className="hint">MediaPipe tracks the index fingertip. YOLOv8m-Worldv2 detects registered object classes; touching a live detection for three seconds activates it.</p>
        </aside>
      </section>

      <footer><span>Local archive / {objects.length} objects</span><a href="/debug">Vision debug →</a><span>Privacy mode / media remains on configured server</span></footer>
    </main>
  )
}
