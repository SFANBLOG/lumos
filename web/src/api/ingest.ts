import apiClient from './client'

export interface FileIngestResponse {
  filename: string
  ext: string
  size: number
  char_count: number
  text: string
  truncated: boolean
  scanned: boolean
  object_name: string
}

export interface UrlIngestResponse {
  url: string
  title: string
  char_count: number
  text: string
  truncated: boolean
}

export const ingestApi = {
  /** multipart 上传走 axios 拦截器, 自动携带 Bearer token */
  async uploadFile(file: File) {
    const form = new FormData()
    form.append('file', file)
    const { data } = await apiClient.post<FileIngestResponse>('/ingest/file', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
    return data
  },
  async ingestUrl(url: string) {
    const { data } = await apiClient.post<UrlIngestResponse>('/ingest/url', { url }, { timeout: 30000 })
    return data
  },
}
