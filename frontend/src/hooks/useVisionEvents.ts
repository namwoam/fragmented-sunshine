import { useEffect, useRef, useState } from 'react'
import type { VisionEvent } from '../types'

export function useVisionEvents(onEvent: (event: VisionEvent) => void) {
  const callback = useRef(onEvent)
  const [connected, setConnected] = useState(false)
  const [lastFrame, setLastFrame] = useState<VisionEvent | null>(null)

  useEffect(() => {
    callback.current = onEvent
  }, [onEvent])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/api/vision/events`)
    socket.onopen = () => setConnected(true)
    socket.onclose = () => setConnected(false)
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as VisionEvent
      if (event.event_type === 'frame') setLastFrame(event)
      callback.current(event)
    }
    return () => socket.close()
  }, [])

  return { connected, lastFrame }
}
