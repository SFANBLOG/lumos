import apiClient from './client'

export interface ContractSubmitRequest {
  text: string
  source?: string
  page_count?: number
}

export interface ContractSubmitResponse {
  contract_id: string
  status: string
  message: string
  stream_url: string
}

export interface SSEvent {
  event: string
  data: any
}

export const contractApi = {
  submit(data: ContractSubmitRequest) {
    return apiClient.post<ContractSubmitResponse>('/contracts', data)
  },
  stream(contractId: string, onEvent: (event: SSEvent) => void) {
    const eventSource = new EventSource(`/api/v1/contracts/${contractId}/stream`)
    eventSource.onmessage = (e) => {
      const lines = e.data.split('\n')
      let event = 'message'
      let data = ''
      lines.forEach((line: string) => {
        if (line.startsWith('event:')) event = line.replace('event:', '').trim()
        if (line.startsWith('data:')) data = line.replace('data:', '').trim()
      })
      if (data) onEvent({ event, data: JSON.parse(data) })
    }
    return eventSource
  },
}
