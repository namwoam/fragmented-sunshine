import { useEffect, useRef, useState } from 'react'
import { useVisionEvents } from '../hooks/useVisionEvents'
import type { VisionEvent } from '../types'

function percentage(value: number) {
  return `${Math.round(value * 100)}%`
}

function cameraUnavailableMessage() {
  const mediaDevices = typeof navigator === 'undefined'
    ? undefined
    : (navigator as { mediaDevices?: MediaDevices }).mediaDevices
  if (mediaDevices?.getUserMedia) return ''
  return window.isSecureContext
    ? 'Camera access is not supported by this browser.'
    : 'Camera access requires HTTPS or localhost.'
}

export function VisionDebug() {
  const [lastEvent, setLastEvent] = useState<VisionEvent | null>(null)
  const [recordingCameraError, setRecordingCameraError] = useState(cameraUnavailableMessage)
  const recordingPreviewRef = useRef<HTMLVideoElement>(null)
  const vision = useVisionEvents((event) => {
    if (event.event_type !== 'frame') setLastEvent(event)
  })
  const frame = vision.lastFrame

  useEffect(() => {
    let active = true
    let stream: MediaStream | null = null
    const mediaDevices = (navigator as { mediaDevices?: MediaDevices }).mediaDevices

    if (!mediaDevices?.getUserMedia) {
      return () => {
        active = false
      }
    }

    void mediaDevices.getUserMedia({ video: true, audio: false })
      .then((nextStream) => {
        if (!active) {
          nextStream.getTracks().forEach((track) => track.stop())
          return
        }
        stream = nextStream
        if (recordingPreviewRef.current) recordingPreviewRef.current.srcObject = nextStream
      })
      .catch((reason) => {
        if (active) {
          setRecordingCameraError(reason instanceof Error ? reason.message : 'Recording camera is unavailable')
        }
      })

    return () => {
      active = false
      stream?.getTracks().forEach((track) => track.stop())
    }
  }, [])

  return (
    <main className="debug-page">
      <nav className="debug-nav">
        <a href="/">← Installation</a>
        <span className={vision.connected ? 'debug-status online' : 'debug-status'}>
          {vision.connected ? 'Live stream connected' : 'Waiting for vision worker'}
        </span>
      </nav>

      <header className="debug-header">
        <p className="eyebrow">Diagnostics / Camera feeds</p>
        <h1>Vision<br />Debug</h1>
        <p className="clock">WebSocket / API vision events</p>
      </header>

      <section className="debug-grid">
        <div className="debug-feeds">
          <section className="debug-feed">
            <div className="section-heading"><span>01</span><h2>Tray camera</h2></div>
            <div className="debug-viewport">
              {frame?.frame_image && <img src={frame.frame_image} alt="Live tray camera" />}
              <svg viewBox="0 0 1000 750" preserveAspectRatio="none">
                <rect className="tray-roi" x="80" y="60" width="840" height="630" />
                <text x="92" y="85">CALIBRATED TRAY ROI</text>
                {frame?.objects.map((object, index) => (
                  <g key={`object-${index}`} className="object-box">
                    <rect
                      x={object.bbox.x1 * 1000}
                      y={object.bbox.y1 * 750}
                      width={(object.bbox.x2 - object.bbox.x1) * 1000}
                      height={(object.bbox.y2 - object.bbox.y1) * 750}
                    />
                    <text x={object.bbox.x1 * 1000} y={object.bbox.y1 * 750 - 9}>
                      {object.object_id ?? object.class_name} / {percentage(object.confidence)}
                    </text>
                  </g>
                ))}
                {frame?.hands.map((hand, index) => (
                  <g key={`hand-${index}`} className={`hand-box ${hand.handedness}`}>
                    <rect
                      x={hand.bbox.x1 * 1000}
                      y={hand.bbox.y1 * 750}
                      width={(hand.bbox.x2 - hand.bbox.x1) * 1000}
                      height={(hand.bbox.y2 - hand.bbox.y1) * 750}
                    />
                    <circle cx={hand.wrist_x * 1000} cy={hand.wrist_y * 750} r="6" />
                    <line
                      x1={hand.wrist_x * 1000}
                      y1={hand.wrist_y * 750}
                      x2={(hand.wrist_x + hand.movement_x * 8) * 1000}
                      y2={(hand.wrist_y + hand.movement_y * 8) * 750}
                    />
                    <text x={hand.bbox.x1 * 1000} y={hand.bbox.y1 * 750 - 9}>
                      {hand.handedness} / {percentage(hand.confidence)}
                    </text>
                  </g>
                ))}
              </svg>
              {!frame?.frame_image && <p className="debug-empty">Start `task vision:dev` to receive the tray feed.</p>}
            </div>
          </section>

          <section className="debug-feed">
            <div className="section-heading"><span>02</span><h2>Recording camera</h2></div>
            <div className="debug-viewport">
              <video ref={recordingPreviewRef} autoPlay muted playsInline />
              {recordingCameraError && <p className="debug-empty">{recordingCameraError}</p>}
            </div>
          </section>
        </div>

        <aside className="debug-data">
          <section>
            <div className="section-heading"><span>03</span><h2>Hands</h2></div>
            {frame?.hands.length ? frame.hands.map((hand, index) => (
              <dl key={index}>
                <dt>{hand.handedness} hand</dt><dd>{percentage(hand.confidence)}</dd>
                <dt>Wrist</dt><dd>{hand.wrist_x.toFixed(3)}, {hand.wrist_y.toFixed(3)}</dd>
                <dt>Movement</dt><dd>{hand.movement_x.toFixed(4)}, {hand.movement_y.toFixed(4)}</dd>
                <dt>Speed</dt><dd>{hand.speed.toFixed(3)} frame/s</dd>
              </dl>
            )) : <p className="empty-row">No hands detected</p>}
          </section>

          <section>
            <div className="section-heading"><span>04</span><h2>Objects</h2></div>
            {frame?.objects.length ? frame.objects.map((object, index) => (
              <dl key={index}>
                <dt>{object.object_id ?? 'Unmapped'}</dt><dd>{percentage(object.confidence)}</dd>
                <dt>YOLO class</dt><dd>{object.class_name}</dd>
                <dt>Tray region</dt><dd>{object.on_tray ? 'inside' : 'outside'}</dd>
              </dl>
            )) : <p className="empty-row">No objects detected</p>}
          </section>

          <section>
            <div className="section-heading"><span>05</span><h2>Last event</h2></div>
            <dl>
              <dt>Type</dt><dd>{lastEvent?.event_type ?? 'none'}</dd>
              <dt>Object</dt><dd>{lastEvent?.object_id ?? '—'}</dd>
              <dt>Hand</dt><dd>{lastEvent?.handedness ?? '—'}</dd>
              <dt>Frame time</dt><dd>{frame ? new Date(frame.timestamp * 1000).toLocaleTimeString() : '—'}</dd>
            </dl>
          </section>
        </aside>
      </section>
    </main>
  )
}
