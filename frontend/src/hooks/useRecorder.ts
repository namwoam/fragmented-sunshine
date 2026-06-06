import { useCallback, useEffect, useRef, useState } from 'react'

export function useRecorder() {
  const previewRef = useRef<HTMLVideoElement>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const [isRecording, setIsRecording] = useState(false)

  const prepare = useCallback(async () => {
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ video: true, audio: true })
    }
    if (previewRef.current) {
      previewRef.current.srcObject = streamRef.current
    }
    return streamRef.current
  }, [])

  const start = useCallback(async () => {
    const stream = await prepare()
    chunksRef.current = []
    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9,opus')
      ? 'video/webm;codecs=vp9,opus'
      : 'video/webm'
    const recorder = new MediaRecorder(stream, { mimeType })
    recorder.ondataavailable = (event) => event.data.size && chunksRef.current.push(event.data)
    recorder.start(500)
    recorderRef.current = recorder
    setIsRecording(true)
  }, [prepare])

  const stop = useCallback(() => new Promise<Blob>((resolve, reject) => {
    const recorder = recorderRef.current
    if (!recorder || recorder.state === 'inactive') {
      reject(new Error('No recording is active'))
      return
    }
    recorder.onstop = () => {
      setIsRecording(false)
      resolve(new Blob(chunksRef.current, { type: recorder.mimeType }))
    }
    recorder.stop()
  }), [])

  useEffect(() => () => streamRef.current?.getTracks().forEach((track) => track.stop()), [])

  return { previewRef, prepare, start, stop, isRecording }
}

