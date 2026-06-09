import type { MemoryObject, Playback } from './types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `Request failed (${response.status})`)
  }
  return response.json() as Promise<T>
}

export const api = {
  objects: () => request<MemoryObject[]>('/api/objects'),
  createObject: (object: Pick<MemoryObject, 'object_id' | 'class_name' | 'display_name' | 'location_x' | 'location_y' | 'touch_radius'>) =>
    request<MemoryObject>('/api/objects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(object),
    }),
  updateObjectLocation: (objectId: string, location: Pick<MemoryObject, 'location_x' | 'location_y' | 'touch_radius'>) =>
    request<MemoryObject>(`/api/objects/${objectId}/location`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(location),
    }),
  uploadRecording: (formData: FormData) =>
    request<{ recording_id: string }>('/api/recordings', { method: 'POST', body: formData }),
  processRecording: (recordingId: string) =>
    request(`/api/recordings/${recordingId}/process`, { method: 'POST' }),
  playback: (objectId: string) => request<Playback>(`/api/objects/${objectId}/playback`),
  savePlayback: (playback: Playback) =>
    request(`/api/objects/${playback.object_id}/playback-events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        recording_id: playback.recording_id,
        timeline: playback.timeline,
        played_at: new Date().toISOString(),
      }),
    }),
}
