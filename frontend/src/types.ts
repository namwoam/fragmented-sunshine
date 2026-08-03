export type MemoryObject = {
  object_id: string
  class_name: string
  display_name: string
  created_at: string
}

export type Segment = {
  segment_id: string
  recording_id: string
  start_time: number
  end_time: number
  transcript_text: string
  video_segment_path: string | null
  sequence_number: number
  media_url: string | null
}

export type Playback = {
  object_id: string
  recording_id: string
  replay_count: number
  timeline: string[]
  segments: Segment[]
  source_url: string | null
}

export type InteractionState = 'on_tray' | 'recording' | 'processing' | 'playing' | 'unavailable'

export type VisionEvent = {
  event_type: 'frame' | 'recording_frame' | 'object_activated' | 'object_released'
  timestamp: number
  frame_image: string | null
  object_id: string | null
  handedness: 'left' | 'right' | null
  hands: Array<{
    handedness: 'left' | 'right'
    confidence: number
    bbox: { x1: number; y1: number; x2: number; y2: number }
    wrist_x: number
    wrist_y: number
    movement_x: number
    movement_y: number
    speed: number
    touch_x: number
    touch_y: number
  }>
  objects: Array<{
    object_id: string | null
    class_name: string
    confidence: number
    bbox: { x1: number; y1: number; x2: number; y2: number }
    on_tray: boolean
  }>
  dwells: Array<{
    object_id: string
    handedness: 'left' | 'right'
    elapsed_seconds: number
    remaining_seconds: number
    progress: number
  }>
  locks: Array<{
    object_id: string
    handedness: 'left' | 'right'
    status: 'live' | 'hand_locked' | 'activated'
    object_visible: boolean
  }>
}
