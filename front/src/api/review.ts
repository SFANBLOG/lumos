import apiClient from './client'

export type FeedbackVerdict = 'accepted' | 'false_positive' | 'ignored'

export interface RiskFeedbackPayload {
  risk_item_id: string
  contract_id: string
  verdict: FeedbackVerdict
  comment?: string
}

export interface RiskFeedbackRecord {
  id: string
  risk_item_id: string
  contract_id: string
  verdict: FeedbackVerdict
  comment: string
  user_id: string | null
  created_at: string
  updated_at: string
}

export interface ReviewStats {
  total: number
  accepted: number
  false_positive: number
  ignored: number
  /** 真实采纳率, 替换 Dashboard 里的演示数字 */
  adoption_rate: number
  /** 误报率 */
  false_positive_rate: number
}

export const reviewApi = {
  /** 对单条 AI 风险结论提交认可 / 误报 / 忽略 */
  submitFeedback(data: RiskFeedbackPayload) {
    return apiClient.post<RiskFeedbackRecord>('/feedback', data)
  },
  listFeedback(contractId: string) {
    return apiClient.get<RiskFeedbackRecord[]>(`/feedback/contracts/${contractId}`)
  },
  /** 真实采纳率与误报率 */
  stats() {
    return apiClient.get<ReviewStats>('/feedback/stats')
  },
}
