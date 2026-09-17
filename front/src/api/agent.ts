import apiClient from './client'

export type ApprovalStatus = 'pending' | 'approved' | 'rejected'

export interface ApprovalTask {
  id: string
  contract_id: string
  status: ApprovalStatus
  comment: string
  created_at: string
  decided_at?: string | null
  can_decide: boolean
  contract_preview: string
  contract_status?: string | null
}

export interface Playbook {
  name: string
  position: string
  rules: string[]
  version: string
  status: string
}

export const agentApi = {
  approvals(status?: ApprovalStatus) {
    return apiClient.get<ApprovalTask[]>('/approvals', { params: status ? { status } : {} })
  },
  decide(taskId: string, status: 'approved' | 'rejected', comment: string) {
    return apiClient.post(`/approvals/${taskId}/decision`, { status, comment })
  },
  activePlaybook() {
    return apiClient.get<Playbook>('/playbooks/active')
  },
}
