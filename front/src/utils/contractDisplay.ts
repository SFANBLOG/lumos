import type { ContractListItem } from '@/api/contract'
import { formatTime, sourceLabel } from '@/utils/contractMeta'

export type ChipTone = 'danger' | 'warn' | 'success' | 'info' | 'primary' | 'muted'

export interface ContractRow {
  id: string
  name: string
  code: string
  type: string
  counterparty: string
  status: string
  progress: number
  issues: number
  level: string
  owner: string
  createdAt: string
  pages: number
  size: string
  source: string
  sourceText: string
  preview: string
  demo: boolean
}

export const OWNERS = ['林墨', '陈屿', '沈禾', '周序', '许知夏']

const CONTRACT_TYPES: Array<{ type: string; words: string[] }> = [
  { type: '技术合同', words: ['开发', '技术', '软件', '系统', '运维', '接口', '网站'] },
  { type: '租赁合同', words: ['租赁', '场地', '房屋', '物业'] },
  { type: '保密协议', words: ['保密', '竞业', '数据安全', '个人信息'] },
  { type: '销售合同', words: ['销售', '经销', '渠道', '订单', '供货'] },
  { type: '采购合同', words: ['采购', '供应', '框架协议', '招标'] },
  { type: '服务合同', words: ['服务', '咨询', '营销', '推广', '外包'] },
  { type: '劳动合同', words: ['劳动', '员工', '试用期', '薪酬'] },
]

export const statusMeta = (status: string): { text: string; tone: ChipTone } => {
  switch (status) {
    case 'analyzing':
      return { text: '审查中', tone: 'primary' }
    case 'reviewing':
      return { text: '待复核', tone: 'warn' }
    case 'completed':
      return { text: '已完成', tone: 'success' }
    case 'failed':
      return { text: '解析失败', tone: 'danger' }
    case 'pending':
    default:
      return { text: '待处理', tone: 'info' }
  }
}

export const levelMeta = (level: string): { text: string; tone: ChipTone; color: string } => {
  switch (level) {
    case 'high':
      return { text: '高风险', tone: 'danger', color: '#e34b4b' }
    case 'medium':
      return { text: '中风险', tone: 'warn', color: '#eda01d' }
    case 'low':
      return { text: '低风险', tone: 'success', color: '#1fae72' }
    case 'safe':
      return { text: '合规', tone: 'success', color: '#1fae72' }
    default:
      return { text: '待分析', tone: 'muted', color: '#a8aec0' }
  }
}

const hash = (text: string) => {
  let value = 0
  for (let i = 0; i < text.length; i += 1) value = (value * 33 + text.charCodeAt(i)) % 99991
  return value
}

export const ownerOf = (id: string) => OWNERS[hash(id) % OWNERS.length]

export const inferContractType = (text: string) => {
  const hit = CONTRACT_TYPES.find((item) => item.words.some((word) => text.includes(word)))
  return hit?.type ?? '服务合同'
}

/** 从 80 字正文预览中尽量还原合同名称 */
export const inferContractName = (preview: string, fallback: string) => {
  const cleaned = preview.replace(/\s+/g, ' ').trim()
  const firstLine = cleaned.split(/[。；;]/)[0] ?? ''
  const candidates = [
    firstLine,
    cleaned.slice(0, 22),
  ]
  const noise = /^(合同编号|甲方|乙方|委托方|受托方|鉴于|依据|本合同)/
  const match = candidates.find((text) => text.length >= 6 && !noise.test(text))
  if (!match) return fallback
  return match.length > 26 ? `${match.slice(0, 26)}…` : match
}

export const inferCounterparty = (text: string) => {
  const pattern = /(?:甲方|乙方|委托方|受托方|相对方|对方)[（(]?[^：:\n]{0,6}[）)]?[：:]\s*([^\n，,；;、]{2,26})/
  const match = text.match(pattern)
  if (!match) return '—'
  return match[1].replace(/（.*?）/g, '').trim()
}

export const contractCode = (id: string, createdAt: string) => {
  const date = (createdAt || '').replace(/[-: T]/g, '').slice(0, 8)
  return `CT-${date || '20260910'}-${id.replace(/-/g, '').slice(0, 3).toUpperCase()}`
}

/** 后端合同记录 → 表格展示行（补齐名称/编号/类型等派生字段） */
export const toContractRow = (item: ContractListItem, index = 0): ContractRow => {
  const preview = item.preview || ''
  const type = inferContractType(preview)
  const idSeed = item.id ?? ''
  return {
    id: item.id,
    name: inferContractName(preview, `${type}（${(idSeed || 'N/A').slice(0, 6)}）`),
    code: contractCode(idSeed, item.created_at),
    type,
    counterparty: inferCounterparty(preview),
    status: item.status,
    progress: item.status === 'completed' ? 100 : item.status === 'analyzing' ? 45 : 0,
    issues: 0,
    level: 'none',
    owner: ownerOf(idSeed || String(index)),
    createdAt: formatTime(item.created_at),
    pages: Math.max(1, Math.ceil((item.char_count ?? 0) / 1800)),
    size: `${(((item.char_count ?? 0) * 2) / 1024 / 1024).toFixed(1)} MB`,
    source: item.source,
    sourceText: sourceLabel(item.source),
    preview,
    demo: false,
  }
}
