import { useState } from 'react'
import { useVisionEvents } from '../hooks/useVisionEvents'
import type { VisionEvent } from '../types'

function percentage(value: number) {
  return `${Math.round(value * 100)}%`
}

export function VisionDebug() {
  const [lastEvent, setLastEvent] = useState<VisionEvent | null>(null)
  const vision = useVisionEvents((event) => {
    if (!['frame', 'recording_frame'].includes(event.event_type)) setLastEvent(event)
  })
  const frame = vision.lastFrame

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
                  <g key={`object-${index}`} className={`object-box${frame.dwells?.some((dwell) => dwell.object_id === object.object_id) ? ' dwelling' : ''}`}>
                    <ellipse
                      cx={(object.bbox.x1 + object.bbox.x2) * 500}
                      cy={(object.bbox.y1 + object.bbox.y2) * 375}
                      rx={(object.bbox.x2 - object.bbox.x1) * 500}
                      ry={(object.bbox.y2 - object.bbox.y1) * 375}
                    />
                    <circle
                      className="object-center"
                      cx={(object.bbox.x1 + object.bbox.x2) * 500}
                      cy={(object.bbox.y1 + object.bbox.y2) * 375}
                      r="5"
                    />
                    <text x={object.bbox.x1 * 1000} y={object.bbox.y1 * 750 - 9}>
                      {object.object_id ?? object.class_name} / {percentage(object.confidence)}
                    </text>
                    {frame.dwells?.filter((dwell) => dwell.object_id === object.object_id).map((dwell) => (
                      <text
                        key={dwell.handedness}
                        className="dwell-label"
                        x={(object.bbox.x1 + object.bbox.x2) * 500}
                        y={(object.bbox.y1 + object.bbox.y2) * 375 + (dwell.handedness === 'left' ? -12 : 18)}
                        textAnchor="middle"
                      >
                        {dwell.handedness} / {dwell.remaining_seconds.toFixed(1)}s
                      </text>
                    ))}
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
                    <circle className="touch-point" cx={hand.touch_x * 1000} cy={hand.touch_y * 750} r="9" />
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
              {vision.recordingFrame?.frame_image && (
                <img src={vision.recordingFrame.frame_image} alt="Live recording camera" />
              )}
              {!vision.recordingFrame?.frame_image && (
                <p className="debug-empty">
                  Start `task vision:dev`; recording camera defaults to index 1.
                </p>
              )}
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
                <dt>Index tip</dt><dd>{hand.touch_x.toFixed(3)}, {hand.touch_y.toFixed(3)}</dd>
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
                <dt>Object type</dt><dd>{object.class_name}</dd>
                <dt>Activation region</dt><dd>{object.on_tray ? 'registered' : 'inactive'}</dd>
                <dt>Center</dt><dd>{((object.bbox.x1 + object.bbox.x2) / 2).toFixed(3)}, {((object.bbox.y1 + object.bbox.y2) / 2).toFixed(3)}</dd>
                <dt>Radius</dt><dd>{((object.bbox.x2 - object.bbox.x1) / 2).toFixed(3)}</dd>
              </dl>
            )) : <p className="empty-row">No objects detected</p>}
          </section>

          <section>
            <div className="section-heading"><span>05</span><h2>Touch countdown</h2></div>
            {frame?.dwells?.length ? frame.dwells.map((dwell) => (
              <dl key={`${dwell.object_id}-${dwell.handedness}`} className="debug-dwell">
                <dt>Object</dt><dd>{dwell.object_id}</dd>
                <dt>Hand</dt><dd>{dwell.handedness}</dd>
                <dt>Remaining</dt><dd>{dwell.remaining_seconds.toFixed(1)} sec</dd>
                <dt>Progress</dt><dd>{percentage(dwell.progress)}</dd>
              </dl>
            )) : <p className="empty-row">No object is being touched</p>}
          </section>

          <section>
            <div className="section-heading"><span>06</span><h2>Last event</h2></div>
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
