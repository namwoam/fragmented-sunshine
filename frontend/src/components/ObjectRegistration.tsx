import { useState } from 'react'
import { api } from '../api'
import type { MemoryObject } from '../types'

type Props = {
  frameImage: string | null
  selectedObject: MemoryObject | undefined
  onSaved: (object: MemoryObject) => void
}

export function ObjectRegistration({ frameImage, selectedObject, onSaved }: Props) {
  const [mode, setMode] = useState<'new' | 'location' | null>(null)
  const [location, setLocation] = useState<{ x: number; y: number } | null>(null)
  const [radius, setRadius] = useState(0.08)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!location) {
      setError('Choose the object location in the tray image')
      return
    }
    const data = new FormData(event.currentTarget)
    try {
      const coordinates = {
        location_x: location.x,
        location_y: location.y,
        touch_radius: radius,
      }
      const object = mode === 'location' && selectedObject
        ? await api.updateObjectLocation(selectedObject.object_id, coordinates)
        : await api.createObject({
            object_id: String(data.get('object_id')),
            class_name: String(data.get('class_name')),
            display_name: String(data.get('display_name')),
            ...coordinates,
          })
      onSaved(object)
      setMode(null)
      setLocation(null)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not register object')
    }
  }

  function chooseLocation(event: React.MouseEvent<HTMLButtonElement>) {
    const bounds = event.currentTarget.getBoundingClientRect()
    setLocation({
      x: (event.clientX - bounds.left) / bounds.width,
      y: (event.clientY - bounds.top) / bounds.height,
    })
    setError('')
  }

  function openLocationEditor() {
    setLocation(selectedObject?.location_x != null && selectedObject.location_y != null
      ? { x: selectedObject.location_x, y: selectedObject.location_y }
      : null)
    setRadius(selectedObject?.touch_radius ?? 0.08)
    setMode('location')
  }

  function openNewObjectEditor() {
    setLocation(null)
    setRadius(0.08)
    setMode('new')
  }

  if (!mode) return (
    <div className="registration-actions">
      <button className="text-button" disabled={!selectedObject} onClick={openLocationEditor}>Set selected location</button>
      <button className="text-button" onClick={openNewObjectEditor}>+ Register new object</button>
    </div>
  )

  return (
    <form className="registration" onSubmit={submit}>
      {mode === 'new' ? <>
        <input name="object_id" placeholder="object_id" pattern="[a-zA-Z0-9_-]+" required />
        <input name="class_name" placeholder="object type" required />
        <input name="display_name" placeholder="display name" required />
      </> : <small>Set location / {selectedObject?.display_name}</small>}
      <label className="radius-field">
        Touch radius / {(radius * 100).toFixed(0)}%
        <input
          name="touch_radius"
          type="range"
          min="0.02"
          max="0.3"
          step="0.01"
          value={radius}
          onChange={(event) => setRadius(Number(event.target.value))}
        />
      </label>
      {frameImage ? (
        <button type="button" className="location-picker" onClick={chooseLocation}>
          <img src={frameImage} alt="Choose the object's fixed tray location" />
          {location && <>
            <span
              className="touch-region"
              style={{
                left: `${location.x * 100}%`,
                top: `${location.y * 100}%`,
                width: `${radius * 200}%`,
                height: `${radius * 200}%`,
              }}
            />
            <span
              className="touch-center"
              style={{ left: `${location.x * 100}%`, top: `${location.y * 100}%` }}
            />
          </>}
        </button>
      ) : <p className="empty-row">Start tray vision to choose a location.</p>}
      {location && <small>Center / {location.x.toFixed(3)}, {location.y.toFixed(3)} / Radius {radius.toFixed(2)}</small>}
      {error && <p className="error">{error}</p>}
      <div><button type="submit">Save location</button><button type="button" className="quiet" onClick={() => setMode(null)}>Cancel</button></div>
    </form>
  )
}
