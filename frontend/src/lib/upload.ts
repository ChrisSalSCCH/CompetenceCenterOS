import api from '@/lib/api'

export interface UploadedFile {
  file_key: string
  size: number
  content_type: string
}

interface UploadTarget {
  upload_key: string
  method: string
  url: string
  headers: Record<string, string>
}

/**
 * Upload straight to object storage with a signed URL, then finalize on the server.
 * Only the finalized `file_key` may be stored; the server checks real size and type.
 */
export async function uploadFile(file: File, folder = ''): Promise<UploadedFile> {
  const { data: target } = await api.post<UploadTarget>('/storage/upload-url', {
    size: file.size,
    content_type: file.type || 'application/octet-stream',
  })
  const res = await fetch(target.url, { method: target.method, headers: target.headers, body: file })
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`)
  const { data } = await api.post<UploadedFile>('/storage/finalize', {
    upload_key: target.upload_key,
    filename: file.name,
    folder,
    is_public: false,
  })
  return data
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return '–'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}
