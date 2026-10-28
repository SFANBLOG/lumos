/** 合同来源/状态/风险等级的展示文案与标签色映射 */

export const sourceLabels: Record<string, string> = {
  text_paste: '粘贴文本',
  file_upload: '文件上传',
  url_analysis: '网页链接',
  pdf_upload: 'PDF 上传',
  word_upload: 'Word 上传',
  camera_ocr: '拍照 OCR',
}

export const statusLabels: Record<string, string> = {
  pending: '等待中',
  analyzing: '分析中',
  completed: '已完成',
  failed: '失败',
}

export const levelLabels: Record<string, string> = {
  high: '高危',
  medium: '警惕',
  low: '关注',
  safe: '合规',
}

export const categoryLabels: Record<string, string> = {
  non_compete: '竞业禁止',
  probation_salary: '试用期薪资',
  probation_insurance: '试用期社保',
  salary_deduction: '扣薪条款',
  job_description: '岗位职责模糊',
  obedience_clause: '服从安排条款',
  resignation: '离职审批',
  leave_rights: '休假权益',
  jurisdiction: '管辖地争议',
  training_bond: '培训服务期',
}

type TagType = 'primary' | 'success' | 'warning' | 'danger' | 'info'

export const sourceLabel = (s: string) => sourceLabels[s] ?? s
export const statusLabel = (s: string) => statusLabels[s] ?? s
export const levelLabel = (s: string) => levelLabels[s] ?? s
export const categoryLabel = (s: string) => categoryLabels[s] ?? s

export const statusTagType = (s: string): TagType => {
  switch (s) {
    case 'completed':
      return 'success'
    case 'analyzing':
      return 'warning'
    case 'failed':
      return 'danger'
    default:
      return 'info'
  }
}

export const sourceTagType = (s: string): TagType => {
  switch (s) {
    case 'file_upload':
      return 'success'
    case 'url_analysis':
      return 'primary'
    case 'pdf_upload':
    case 'word_upload':
    case 'camera_ocr':
      return 'warning'
    default:
      return 'info'
  }
}

export const levelTagType = (l: string): TagType => {
  switch (l) {
    case 'high':
      return 'danger'
    case 'medium':
      return 'warning'
    case 'safe':
      return 'success'
    default:
      return 'info'
  }
}

export const levelColor = (l: string): string => {
  switch (l) {
    case 'high':
      return '#f56c6c'
    case 'medium':
      return '#e6a23c'
    case 'safe':
      return '#67c23a'
    default:
      return '#409eff'
  }
}

/** 服务端 DATETIME 为 UTC 朴素值, 补 Z 后按东八区渲染 */
export const formatTime = (iso: string) => {
  const normalized = iso.includes('Z') || iso.includes('+') ? iso : `${iso}Z`
  const d = new Date(normalized)
  if (Number.isNaN(d.getTime())) return iso
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(d)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? '00'
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
}
