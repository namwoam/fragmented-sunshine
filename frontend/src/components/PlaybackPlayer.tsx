import { useEffect, useMemo, useRef, useState } from 'react'
import type { Playback, Segment } from '../types'

type Props = {
  playback: Playback
  onComplete: () => void
}

export function PlaybackPlayer({ playback, onComplete }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const completedRef = useRef(false)
  const [position, setPosition] = useState(0)
  const orderedSegments = useMemo(() => {
    const byId = new Map(playback.segments.map((segment) => [segment.segment_id, segment]))
    return playback.timeline.map((id) => byId.get(id)).filter(Boolean) as Segment[]
  }, [playback])
  const segment = orderedSegments[position]

  useEffect(() => {
    if (segment || completedRef.current) return
    completedRef.current = true
    onComplete()
  }, [segment, onComplete])

  useEffect(() => {
    const video = videoRef.current
    if (!video || !segment) return
    let advanced = false
    const finishSegment = () => {
      if (advanced) return
      advanced = true
      if (position + 1 < orderedSegments.length) {
        setPosition((value) => value + 1)
      } else if (!completedRef.current) {
        completedRef.current = true
        onComplete()
      }
    }
    const source = segment.media_url ?? playback.source_url
    if (!source) {
      finishSegment()
      return
    }

    const fullSource = source
    if (video.getAttribute('src') !== fullSource) {
      video.src = fullSource
    }
    const begin = () => {
      if (!segment.media_url) video.currentTime = segment.start_time
      void video.play()
    }
    if (video.readyState >= 1) begin()
    else video.addEventListener('loadedmetadata', begin, { once: true })

    const checkProgress = () => {
      const finished = segment.media_url ? video.ended : video.currentTime >= segment.end_time
      if (finished) finishSegment()
    }
    video.addEventListener('ended', finishSegment)
    video.addEventListener('timeupdate', checkProgress)
    const timer = window.setInterval(checkProgress, 100)
    return () => {
      window.clearInterval(timer)
      video.removeEventListener('ended', finishSegment)
      video.removeEventListener('timeupdate', checkProgress)
    }
  }, [segment, position, orderedSegments.length, playback.source_url, onComplete])

  if (!segment) return <p className="empty">No playable fragments.</p>

  return (
    <div className="player">
      <video ref={videoRef} playsInline controls={false} />
      <div className="player-caption">
        <span>{String(position + 1).padStart(2, '0')} / {String(orderedSegments.length).padStart(2, '0')}</span>
        <p>{segment.transcript_text}</p>
      </div>
    </div>
  )
}
