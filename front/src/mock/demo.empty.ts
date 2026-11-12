/**
 * 非演示模式下的空数据实现。
 *
 * vite.config.ts 在 VITE_DEMO_MODE !== 'true' 时把 @/mock/demo 指向本文件，
 * 因此所有页面无需逐个改判断，也不会把示例合同 / 示例统计数字带进生产包。
 * 导出的名称与类型必须与 demo.ts 完全一致，保证 vue-tsc 类型检查通过。
 */

import type {
  DemoContract,
  DemoKnowledgeCategory,
  DemoKnowledgeItem,
  DemoReport,
  DemoRuleSet,
} from './demo'

export type {
  DemoContract,
  DemoKnowledgeCategory,
  DemoKnowledgeItem,
  DemoReport,
  DemoRule,
  DemoRuleSet,
} from './demo'

export const DEMO_CONTRACTS: DemoContract[] = []

/** 非演示模式不预填任何合同正文，避免把示例文本当成真实合同提交。 */
export const DEMO_CONTRACT_TEXT = ''

export const DEMO_TREND: { label: string; bars: number; line: number }[] = []

export const DEMO_MONTH_STATS = {
  contracts: 0,
  contractsDelta: '+0%',
  pendingTips: 0,
  pendingHigh: 0,
  todayWaiting: 0,
  avgMinutes: 0,
  avgDelta: '0%',
  adoption: 0,
  adoptionDelta: '+0%',
}

export const DEMO_RISK_OVERVIEW = { high: 0, medium: 0, low: 0 }

export const DEMO_REPORTS: DemoReport[] = []

export const DEMO_REPORT_STATS = {
  monthly: 0,
  avgMinutes: 0,
  resolveRate: 0,
}

/** 分类标签是真实 UI 结构，计数一律为 0，不伪造知识库规模。 */
export const DEMO_KNOWLEDGE_CATEGORIES: DemoKnowledgeCategory[] = [
  { key: 'law', title: '法律法规库', desc: '', count: 0 },
  { key: 'policy', title: '企业制度库', desc: '', count: 0 },
  { key: 'template', title: '标准模板库', desc: '', count: 0 },
  { key: 'case', title: '历史案例库', desc: '', count: 0 },
]

export const DEMO_KNOWLEDGE_ITEMS: DemoKnowledgeItem[] = []

export const DEMO_RULE_SETS: DemoRuleSet[] = []
