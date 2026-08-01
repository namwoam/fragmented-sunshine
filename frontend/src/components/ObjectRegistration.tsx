import { useState } from 'react'
import { api } from '../api'
import type { MemoryObject } from '../types'

type Props = {
  onSaved: (object: MemoryObject) => void
}

export function ObjectRegistration({ onSaved }: Props) {
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    try {
      const object = await api.createObject({
        object_id: String(data.get('object_id')),
        class_name: String(data.get('class_name')),
        display_name: String(data.get('display_name')),
      })
      onSaved(object)
      setOpen(false)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not register object')
    }
  }

  if (!open) return (
    <div className="registration-actions">
      <button className="text-button" onClick={() => setOpen(true)}>+ Register new object</button>
    </div>
  )

  return (
    <form className="registration" onSubmit={submit}>
      <input name="object_id" placeholder="object_id" pattern="[a-zA-Z0-9_-]+" required />
      <input name="class_name" placeholder="visual class prompt, e.g. perfume bottle" required />
      <input name="display_name" placeholder="display name" required />
      <small>YOLO-World will locate this object from its visual class prompt.</small>
      {error && <p className="error">{error}</p>}
      <div><button type="submit">Register object</button><button type="button" className="quiet" onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  )
}
