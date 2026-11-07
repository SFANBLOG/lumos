import apiClient from './client'

/** 文档类型判定结果 (后端 services/contract_guard.py 下发) */
export interface DocCheck {
  doc_type: string
  doc_type_label: string
  is_contract: boolean
  confidence: number
  /** rule=规则判定 llm=模型判定 ext=文件类型判定 */
  method: string
  reasons: string[]
  /** 给用户看的提示文案, 空表示无需提示 */
  notice: string | null
}

/** PDF 解析链路元信息 (后端 services/mineru_parser.py 下发) */
export interface ParseMeta {
  /** mineru=MinerU 版面解析, legacy=内置 pypdf/PyMuPDF/OCR */
  parser: string
  /** 具体引擎: mineru:cli:v4 | mineru:cli:v2 | mineru:http | 内置链路描述 */
  detail: string
  blocks: number
  images: number
  vision_enriched: number
  /** auto 策略回退原因, 空表示未回退 */
  fallback_reason: string
}

export interface FileIngestResponse {
  filename: string
  ext: string
  size: number
  char_count: number
  text: string
  truncated: boolean
  scanned: boolean
  object_name: string
  doc_check?: DocCheck
  parse_meta?: ParseMeta
}

export interface UrlIngestResponse {
  url: string
  title: string
  char_count: number
  text: string
  truncated: boolean
  doc_check?: DocCheck
}

/** 纯文本预览判定响应 (粘贴入口提交前轻量判定) */
export interface TextIngestResponse {
  char_count: number
  text: string
  truncated: boolean
  doc_check?: DocCheck
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
  /** 纯文本预览判定: 粘贴入口在提交前调用, 不落库 */
  async checkText(text: string) {
    const { data } = await apiClient.post<TextIngestResponse>('/ingest/text', { text }, { timeout: 20000 })
    return data
  },
}
