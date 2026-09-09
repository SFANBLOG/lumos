import apiClient from './client'

export interface ConsultRef {
  law_name: string
  article: string
  content: string
  similarity: number
}

export interface ConsultSession {
  id: string
  title: string
  contract_id: string | null
  created_at: string
  updated_at: string
  message_count: number
}

export interface ConsultSessionList {
  total: number
  page: number
  page_size: number
  items: ConsultSession[]
}

export interface ConsultMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  references: ConsultRef[] | null
  suggestions: string[] | null
  created_at: string
}

export interface ConsultAskBody {
  question: string
  session_id?: string | null
  contract_id?: string | null
}

export type ConsultEventType =
  | 'session'
  | 'step'
  | 'answer'
  | 'complete'
  | 'error'

export const consultApi = {
  sessions(page = 1, pageSize = 20) {
    return apiClient.get<ConsultSessionList>('/consult/sessions', {
      params: { page, page_size: pageSize },
    })
  },
  messages(sessionId: string) {
    return apiClient.get<ConsultMessage[]>(`/consult/sessions/${sessionId}/messages`)
  },
  remove(sessionId: string) {
    return apiClient.delete(`/consult/sessions/${sessionId}`)
  },
}

/**
 * POST 版 SSE: 原生 fetch 逐帧解析 `event:` / `data:` 事件.
 *
 * EventSource 不支持 POST body 与自定义鉴权头, 这里手动读流,
 * 以空行分帧, 残帧缓冲到下一块。
 */
export async function askConsult(
  body: ConsultAskBody,
  onEvent: (type: ConsultEventType, data: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = localStorage.getItem('token')
  const resp = await fetch('/api/v1/consult/ask', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  })

  if (!resp.ok || !resp.body) {
    let detail = `请求失败 (HTTP ${resp.status})`
    try {
      const err = await resp.json()
      detail = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail ?? err)
    } catch {
      /* 保留默认文案 */
    }
    throw new Error(detail)
  }

  const decoder = new TextDecoder()
  const reader = resp.body.getReader()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep = buffer.indexOf('\n\n')
    while (sep >= 0) {
      const frame = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const eventLine = frame.split('\n').find((l) => l.startsWith('event: '))
      const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
      if (eventLine && dataLine) {
        const type = eventLine.slice(7).trim() as ConsultEventType
        try {
          onEvent(type, JSON.parse(dataLine.slice(6)))
        } catch {
          onEvent(type, dataLine.slice(6))
        }
      }
      sep = buffer.indexOf('\n\n')
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) {
    // 流结束前若帧缓冲被截断, 尝试按完整帧再次解析
    const frame = buffer.trim()
    const eventLine = frame.split('\n').find((l) => l.startsWith('event: '))
    const dataLine = frame.split('\n').find((l) => l.startsWith('data: '))
    if (eventLine && dataLine) {
      const type = eventLine.slice(7).trim() as ConsultEventType
      try {
        onEvent(type, JSON.parse(dataLine.slice(6)))
      } catch {
        onEvent(type, dataLine.slice(6))
      }
    }
  }
}
