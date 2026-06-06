type CachedRecording = {
  id?: number
  objectId: string
  startedAt: string
  endedAt: string
  blob: Blob
}

const DATABASE = 'fragmented-sunshine'
const STORE = 'pending-recordings'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, {
      keyPath: 'id',
      autoIncrement: true,
    })
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function cacheRecording(recording: CachedRecording): Promise<void> {
  const database = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const transaction = database.transaction(STORE, 'readwrite')
    transaction.objectStore(STORE).add(recording)
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
  database.close()
}

export async function retryCachedRecordings(
  upload: (recording: CachedRecording) => Promise<void>,
): Promise<number> {
  const database = await openDatabase()
  const recordings = await new Promise<CachedRecording[]>((resolve, reject) => {
    const request = database.transaction(STORE).objectStore(STORE).getAll()
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  let uploaded = 0
  for (const recording of recordings) {
    try {
      await upload(recording)
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE, 'readwrite')
        transaction.objectStore(STORE).delete(recording.id!)
        transaction.oncomplete = () => resolve()
        transaction.onerror = () => reject(transaction.error)
      })
      uploaded += 1
    } catch {
      // Leave failed records queued for the next startup.
    }
  }
  database.close()
  return uploaded
}
