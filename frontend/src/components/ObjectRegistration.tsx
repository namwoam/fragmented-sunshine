import { useState } from 'react'
import { api } from '../api'
import type { MemoryObject } from '../types'

export function ObjectRegistration({ onCreated }: { onCreated: (object: MemoryObject) => void }) {
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
      onCreated(object)
      setOpen(false)
      setError('')
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not register object')
    }
  }

  if (!open) return <button className="text-button" onClick={() => setOpen(true)}>+ Register object</button>

  return (
    <form className="registration" onSubmit={submit}>
      <input name="object_id" placeholder="object_id" pattern="[a-zA-Z0-9_-]+" required />
      <input name="class_name" placeholder="class name" required />
      <input name="display_name" placeholder="display name" required />
      {error && <p className="error">{error}</p>}
      <div><button type="submit">Add</button><button type="button" className="quiet" onClick={() => setOpen(false)}>Cancel</button></div>
    </form>
  )
}

