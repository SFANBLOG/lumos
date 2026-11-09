import apiClient from './client'

export interface ContractSubmitRequest {
  text: string
  source?: string
  page_count?: number
  /** 内容判定为「非合同」时, 用户二次确认后传 true 强制继续分析 */
  force?: boolean
}

export interface ContractSubmitResponse {
  contract_id: string
  status: string
  message: string
  stream_url: string
}

export interface ContractListItem {
  id: string
  source: string
  status: string
  char_count: number | null
  doc_type?: string | null
  doc_check_note?: string | null
  created_at: string
  preview: string
}

export interface ContractListResponse {
  total: number
  page: number
  page_size: number
  items: ContractListItem[]
}

export interface ContractStats {
  total: number
  completed: number
  analyzing: number
  failed: number
  pending: number
  avg_overall_score: number | null
  high_risk_contracts: number
  level_counts: { high: number; medium: number; low: number; safe: number }
  recent: ContractListItem[]
}

export interface RiskItemData {
  /** 风险条目 ID, 提交反馈时使用 (演示数据没有) */
  id?: string
  category: string
  level: string
  title: string
  original_clause: string
  explanation: string
  legal_basis: string
  negotiation_tip: string
  /** 条款级修改建议 (redline): 这一条应改成什么文本 */
  suggested_revision?: string
  score: number
}

export interface ContractFactData {
  key: string
  label: string
  value: string
  evidence: string
  confidence: number
  status: string
  required: boolean
  legal_basis: string
}

export interface MissingClauseData {
  key: string
  label: string
  reason: string
  legal_basis: string
  suggested_text: string
  level: string
  score: number
}

export interface AnalysisReport {
  contract_id: string
  overall_score: number
  overall_level: string
  summary: string
  risk_items: RiskItemData[]
  /** 合同要素核对表 (带原文定位与置信度) */
  contract_facts?: ContractFactData[]
  /** 缺失/漏填的必备条款清单 */
  missing_clauses?: MissingClauseData[]
  /** 必备条款覆盖率, 独立于 overall_score 与 confidence_score */
  coverage_score?: number
  /** 内容提示: 提交内容被判定为疑似非合同时给出 */
  content_notice?: string | null
  analyzed_at: string
}

export interface SSEvent {
  event: string
  data: any
}

export const contractApi = {
  list(params: { page?: number; page_size?: number; status?: string }) {
    return apiClient.get<ContractListResponse>('/contracts', { params })
  },
  stats() {
    return apiClient.get<ContractStats>('/contracts/stats')
  },
  submit(data: ContractSubmitRequest) {
    return apiClient.post<ContractSubmitResponse>('/contracts', data)
  },
  get(contractId: string) {
    return apiClient.get(`/contracts/${contractId}`)
  },
  getReport(contractId: string) {
    return apiClient.get<AnalysisReport>(`/contracts/${contractId}/report`)
  },
  /** 后端带批注报告导出 (Markdown / Word), 返回二进制内容 */
  exportReport(contractId: string, format: 'md' | 'docx' = 'docx') {
    return apiClient.get(`/contracts/${contractId}/report/export`, {
      params: { format },
      responseType: 'blob',
    })
  },
  /**
   * 订阅 SSE 分析流.
   *
   * 后端所有事件均带命名 `event:` 字段，而浏览器对命名事件不会触发
   * `onmessage`，因此必须为每个事件名显式注册 addEventListener，
   * `onmessage` 仅作无命名事件的兜底。
   */
  stream(contractId: string, onEvent: (event: SSEvent) => void) {
    const eventSource = new EventSource(`/api/v1/contracts/${contractId}/stream`)
    const names = [
      'thinking',
      'node_start',
      'node_complete',
      'risk_found',
      'summary',
      'complete',
      'error',
    ]
    const dispatch = (event: string, raw: string) => {
      let data: any = raw
      try {
        data = JSON.parse(raw)
      } catch {
        /* 非 JSON 负载原样透传 */
      }
      onEvent({ event, data })
    }
    names.forEach((name) => {
      eventSource.addEventListener(name, (e: MessageEvent) => dispatch(name, e.data))
    })
    eventSource.onmessage = (e: MessageEvent) => dispatch('message', e.data)
    return eventSource
  },
}
