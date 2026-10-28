/**
 * 演示数据：用于在空库 / 接口不可用时展示完整的「契智」工作台形态。
 * 真实接口一旦有数据，页面优先渲染真实数据。
 */

export interface DemoContract {
  id: string
  name: string
  code: string
  type: string
  counterparty: string
  status: 'pending' | 'analyzing' | 'reviewing' | 'completed' | 'failed'
  progress: number
  issues: number
  level: 'high' | 'medium' | 'low' | 'safe' | 'none'
  owner: string
  createdAt: string
  pages: number
  size: string
}

export const DEMO_CONTRACTS: DemoContract[] = [
  {
    id: 'a1f3c9d2-8b41-4e77-9a10-1f2e3d4c5b60',
    name: '云服务采购框架协议',
    code: 'CT-20260910-018',
    type: '采购合同',
    counterparty: '北京星澜科技有限公司',
    status: 'pending',
    progress: 0,
    issues: 12,
    level: 'high',
    owner: '陈屿',
    createdAt: '2026-09-10 09:24',
    pages: 18,
    size: '2.4 MB',
  },
  {
    id: 'b2e4d0e3-9c52-4f88-8b21-2a3f4e5d6c71',
    name: '品牌年度营销服务合同',
    code: 'CT-20260909-063',
    type: '服务合同',
    counterparty: '上海拾光文化传媒',
    status: 'reviewing',
    progress: 100,
    issues: 8,
    level: 'medium',
    owner: '沈禾',
    createdAt: '2026-09-09 16:48',
    pages: 12,
    size: '1.8 MB',
  },
  {
    id: 'c3f5e1f4-0d63-4a99-9c32-3b4a5f6e7d82',
    name: '办公场地租赁合同',
    code: 'CT-20260909-041',
    type: '租赁合同',
    counterparty: '中嘉置业有限公司',
    status: 'analyzing',
    progress: 72,
    issues: 0,
    level: 'none',
    owner: '林墨',
    createdAt: '2026-09-09 13:05',
    pages: 9,
    size: '980 KB',
  },
  {
    id: 'd4a6f2a5-1e74-4b00-ad43-4c5b6a7f8e93',
    name: '软件开发及技术支持协议',
    code: 'CT-20260908-027',
    type: '技术合同',
    counterparty: '深圳云舟数字技术',
    status: 'completed',
    progress: 100,
    issues: 5,
    level: 'low',
    owner: '周序',
    createdAt: '2026-09-08 11:20',
    pages: 15,
    size: '3.1 MB',
  },
  {
    id: 'e5b7a3b6-2f85-4c11-be54-5d6c7b8a9fa4',
    name: '员工保密与竞业限制协议',
    code: 'CT-20260907-019',
    type: '保密协议',
    counterparty: '内部员工',
    status: 'completed',
    progress: 100,
    issues: 7,
    level: 'medium',
    owner: '许知夏',
    createdAt: '2026-09-07 15:42',
    pages: 6,
    size: '640 KB',
  },
  {
    id: 'f6c8b4c7-3a96-4d22-cf65-6e7d8c9b0ab5',
    name: '渠道经销合作协议',
    code: 'CT-20260906-009',
    type: '销售合同',
    counterparty: '杭州远帆商贸有限公司',
    status: 'failed',
    progress: 0,
    issues: 0,
    level: 'none',
    owner: '陈屿',
    createdAt: '2026-09-06 10:15',
    pages: 21,
    size: '4.2 MB',
  },
  {
    id: 'a7d9c5d8-4b07-4e33-d076-7f8e9d0c1bc6',
    name: '技术服务外包合同',
    code: 'CT-20260905-014',
    type: '技术合同',
    counterparty: '成都智算科技有限公司',
    status: 'pending',
    progress: 0,
    issues: 9,
    level: 'high',
    owner: '林墨',
    createdAt: '2026-09-05 17:32',
    pages: 14,
    size: '2.0 MB',
  },
  {
    id: 'b8e0d6e9-5c18-4f44-e187-8a9f0e1d2cd7',
    name: '数据处理与保密协议',
    code: 'CT-20260904-006',
    type: '保密协议',
    counterparty: '广州云链信息技术',
    status: 'completed',
    progress: 100,
    issues: 3,
    level: 'low',
    owner: '沈禾',
    createdAt: '2026-09-04 09:58',
    pages: 8,
    size: '1.1 MB',
  },
]

export const DEMO_TREND = [
  { label: '05/04', bars: 12, line: 9 },
  { label: '05/05', bars: 13, line: 11 },
  { label: '05/06', bars: 11, line: 8 },
  { label: '05/07', bars: 19, line: 15 },
  { label: '05/08', bars: 15, line: 11 },
  { label: '05/09', bars: 24, line: 22 },
  { label: '今天', bars: 20, line: 14 },
]

export const DEMO_MONTH_STATS = {
  contracts: 128,
  contractsDelta: '+8.6%',
  pendingTips: 36,
  pendingHigh: 9,
  todayWaiting: 3,
  avgMinutes: 2.8,
  avgDelta: '-32.4%',
  adoption: 76.4,
  adoptionDelta: '+5.2%',
}

export const DEMO_RISK_OVERVIEW = { high: 48, medium: 126, low: 210 }

export interface DemoReport {
  id: string
  code: string
  contractName: string
  contractId: string
  level: 'high' | 'medium' | 'low' | 'safe'
  issues: number
  owner: string
  finishedAt: string
  pages: number
}

export const DEMO_REPORTS: DemoReport[] = [
  {
    id: 'rpt-018',
    code: 'RPT-20260910-018',
    contractName: '云服务采购框架协议',
    contractId: DEMO_CONTRACTS[0].id,
    level: 'high',
    issues: 12,
    owner: '陈屿',
    finishedAt: '2026-09-10 10:02',
    pages: 18,
  },
  {
    id: 'rpt-063',
    code: 'RPT-20260909-063',
    contractName: '品牌年度营销服务合同',
    contractId: DEMO_CONTRACTS[1].id,
    level: 'medium',
    issues: 8,
    owner: '沈禾',
    finishedAt: '2026-09-09 17:31',
    pages: 12,
  },
  {
    id: 'rpt-027',
    code: 'RPT-20260908-027',
    contractName: '软件开发及技术支持协议',
    contractId: DEMO_CONTRACTS[3].id,
    level: 'low',
    issues: 5,
    owner: '周序',
    finishedAt: '2026-09-08 13:46',
    pages: 15,
  },
  {
    id: 'rpt-012',
    code: 'RPT-20260907-012',
    contractName: '员工保密与竞业限制协议',
    contractId: DEMO_CONTRACTS[4].id,
    level: 'medium',
    issues: 7,
    owner: '许知夏',
    finishedAt: '2026-09-07 16:55',
    pages: 6,
  },
  {
    id: 'rpt-006',
    code: 'RPT-20260904-006',
    contractName: '数据处理与保密协议',
    contractId: DEMO_CONTRACTS[7].id,
    level: 'low',
    issues: 3,
    owner: '沈禾',
    finishedAt: '2026-09-04 11:12',
    pages: 8,
  },
]

export const DEMO_REPORT_STATS = {
  monthly: 86,
  avgMinutes: 18.6,
  resolveRate: 91.8,
}

export interface DemoKnowledgeCategory {
  key: 'law' | 'policy' | 'template' | 'case'
  title: string
  desc: string
  count: number
}

export const DEMO_KNOWLEDGE_CATEGORIES: DemoKnowledgeCategory[] = [
  { key: 'law', title: '法律法规库', desc: '国家法律、行政法规及司法解释', count: 326 },
  { key: 'policy', title: '企业制度库', desc: '采购、财务、数据及内控制度', count: 84 },
  { key: 'template', title: '标准模板库', desc: '各类合同模板及标准条款', count: 56 },
  { key: 'case', title: '历史案例库', desc: '已归档的历史审查案例', count: 218 },
]

export interface DemoKnowledgeItem {
  id: string
  name: string
  category: string
  categoryKey: 'law' | 'policy' | 'template' | 'case'
  version: string
  updatedAt: string
  chunks: number
  status: '已生效' | '已发布' | '草稿'
  cover: 'law' | 'policy' | 'template' | 'case'
}

export const DEMO_KNOWLEDGE_ITEMS: DemoKnowledgeItem[] = [
  {
    id: 'kb-001',
    name: '中华人民共和国民法典（合同编）',
    category: '法律法规',
    categoryKey: 'law',
    version: '2026-01-01',
    updatedAt: '2026-09-08',
    chunks: 1264,
    status: '已生效',
    cover: 'law',
  },
  {
    id: 'kb-002',
    name: '采购合同审查指引 V3.2',
    category: '企业制度',
    categoryKey: 'policy',
    version: '2026-08-28',
    updatedAt: '2026-09-08',
    chunks: 186,
    status: '已发布',
    cover: 'policy',
  },
  {
    id: 'kb-003',
    name: '云服务采购合同标准模板',
    category: '合同模板',
    categoryKey: 'template',
    version: '2026-07-12',
    updatedAt: '2026-09-08',
    chunks: 92,
    status: '已发布',
    cover: 'template',
  },
  {
    id: 'kb-004',
    name: '数据安全管理制度',
    category: '企业制度',
    categoryKey: 'policy',
    version: '2026-06-30',
    updatedAt: '2026-09-08',
    chunks: 144,
    status: '已发布',
    cover: 'policy',
  },
  {
    id: 'kb-005',
    name: '最高人民法院合同编通则司法解释',
    category: '司法解释',
    categoryKey: 'law',
    version: '2023-12-05',
    updatedAt: '2026-09-06',
    chunks: 538,
    status: '已生效',
    cover: 'law',
  },
  {
    id: 'kb-006',
    name: '2026 年 SaaS 采购争议复盘',
    category: '历史案例',
    categoryKey: 'case',
    version: '2026-05-18',
    updatedAt: '2026-09-02',
    chunks: 64,
    status: '已发布',
    cover: 'case',
  },
]

export interface DemoRule {
  id: string
  title: string
  desc: string
  category: string
  level: 'high' | 'medium' | 'low'
  enabled: boolean
}

export interface DemoRuleSet {
  id: string
  name: string
  version: string
  contractType: string
  ruleCount: number
  status: '已发布' | '草稿'
  updatedAt: string
  summary: string
  rules: DemoRule[]
}

export const DEMO_RULE_SETS: DemoRuleSet[] = [
  {
    id: 'rs-001',
    name: '采购合同审查规则',
    version: 'V3.2',
    contractType: '采购合同',
    ruleCount: 42,
    status: '已发布',
    updatedAt: '2026-08-28',
    summary: '适用于公司作为采购方签订的货物、服务及软件采购合同。',
    rules: [
      {
        id: 'r-1',
        title: '预付款比例检查',
        desc: '预付款比例 > 30% 且无履约担保时提示高风险',
        category: '付款条款',
        level: 'high',
        enabled: true,
      },
      {
        id: 'r-2',
        title: '责任上限合理性检查',
        desc: '责任上限显著低于合同金额或赔付范围不足',
        category: '违约责任',
        level: 'high',
        enabled: true,
      },
      {
        id: 'r-3',
        title: '验收流程完整性',
        desc: '缺少验收期限、标准或整改机制',
        category: '交付与验收',
        level: 'medium',
        enabled: true,
      },
      {
        id: 'r-4',
        title: '数据返还与删除',
        desc: '数据处理合同终止后未约定删除及证明义务',
        category: '数据安全',
        level: 'medium',
        enabled: true,
      },
      {
        id: 'r-5',
        title: '争议解决管辖地',
        desc: '约定由对方所在地法院专属管辖',
        category: '争议解决',
        level: 'low',
        enabled: false,
      },
    ],
  },
  {
    id: 'rs-002',
    name: '销售合同审查规则',
    version: 'V2.6',
    contractType: '销售合同',
    ruleCount: 38,
    status: '已发布',
    updatedAt: '2026-08-16',
    summary: '适用于对外销售、渠道经销与框架订单类合同。',
    rules: [
      {
        id: 'r-21',
        title: '账期与信用额度',
        desc: '账期超过 90 天且未约定信用额度与暂停供货权',
        category: '付款条款',
        level: 'high',
        enabled: true,
      },
      {
        id: 'r-22',
        title: '质量异议期',
        desc: '质量异议期短于行业惯例或法律规定',
        category: '交付与验收',
        level: 'medium',
        enabled: true,
      },
      {
        id: 'r-23',
        title: '价格调整机制',
        desc: '原材料价格波动时的调价触发条件与举证方式',
        category: '价格条款',
        level: 'low',
        enabled: true,
      },
    ],
  },
  {
    id: 'rs-003',
    name: '技术服务合同审查规则',
    version: 'V2.1',
    contractType: '技术合同',
    ruleCount: 35,
    status: '已发布',
    updatedAt: '2026-07-30',
    summary: '覆盖软件开发、运维、技术支持等服务的知识产权与验收口径。',
    rules: [
      {
        id: 'r-31',
        title: '知识产权归属',
        desc: '定制开发成果未约定归委托方所有或未约定许可范围',
        category: '知识产权',
        level: 'high',
        enabled: true,
      },
      {
        id: 'r-32',
        title: '验收标准可量化',
        desc: '验收标准缺少功能清单、性能指标或缺陷分级',
        category: '交付与验收',
        level: 'medium',
        enabled: true,
      },
    ],
  },
  {
    id: 'rs-004',
    name: '劳动合同合规规则',
    version: 'V4.0',
    contractType: '劳动合同',
    ruleCount: 27,
    status: '草稿',
    updatedAt: '2026-09-05',
    summary: '对齐最新劳动法与竞业限制司法解释，待法务负责人审批后发布。',
    rules: [
      {
        id: 'r-41',
        title: '竞业限制补偿金',
        desc: '未约定竞业限制经济补偿或低于当地最低工资标准',
        category: '离职与竞业',
        level: 'high',
        enabled: true,
      },
      {
        id: 'r-42',
        title: '试用期期限',
        desc: '试用期超过法定上限或重复约定试用期',
        category: '试用与转正',
        level: 'high',
        enabled: true,
      },
    ],
  },
]

/** 示例合同正文：无真实数据时用于文档图片预览 */
export const DEMO_CONTRACT_TEXT = `网站开发技术服务合同

合同编号：QZ-2026-0910-018

甲方（委托方）：星澜科技有限公司
法定代表人：陈启明
地址：北京市海淀区中关村南大街 18 号
联系方式：010-8888 6600
电子邮箱：legal@xinglan-tech.com

乙方（受托方）：云舟数字技术有限公司
法定代表人：周序
地址：广东省深圳市南山区科技园南区 12 栋
联系方式：0755-2666 8899
电子邮箱：contract@yunzhou-digital.com

依据《中华人民共和国民法典》及相关法律法规，甲乙双方本着平等自愿、诚实信用原则，就甲方委托乙方开发网站事宜，订立本合同，以资共同信守。

第一章 项目概况与范围

第一条 项目基本信息
1. 项目名称：企业官网及客户门户网站开发项目
2. 开发内容：PC 端官网、移动端适配、内容管理系统、数据看板
3. 项目周期：自合同生效之日起 90 个自然日内完成上线
4. 交付形式：源代码、部署文档、操作手册及验收报告

第二条 项目价款
1. 本合同总价款为人民币 860,000 元（大写：捌拾陆万元整），含税。
2. 付款方式：合同签订后 5 个工作日内，甲方向乙方支付合同总价款的 40% 作为预付款；项目验收通过后支付 50%；剩余 10% 作为质保金，于质保期满后支付。
3. 乙方应在收到每笔款项前向甲方开具等额增值税专用发票。

第二章 双方权利义务

第三条 甲方权利义务
1. 甲方应在本合同生效后 10 个工作日内向乙方提供项目所需的基础资料与品牌素材。
2. 甲方有权对项目进度和质量进行监督，并指定项目对接人。
3. 甲方应按约定时间组织验收，逾期未验收且未提出书面异议的，视为验收通过。

第四条 乙方权利义务
1. 乙方应按照项目计划书组织开发，确保系统功能符合需求文档约定。
2. 乙方应保证交付成果不侵犯任何第三方的知识产权。
3. 乙方应对甲方提供的商业信息、技术资料承担永久保密义务，未经甲方书面许可，不得向任何第三方披露。

第三章 知识产权

第五条 知识产权归属
1. 本项目定制开发形成的源代码、设计稿及相关文档，其著作权归甲方所有。
2. 乙方在项目开始前已有的通用组件、框架及工具，其知识产权仍归乙方所有，乙方授予甲方永久、免费、可转授的使用许可。
3. 乙方不得将本项目成果用于与甲方存在竞争关系的第三方项目。

第四章 验收与质保

第六条 验收标准
1. 系统功能应完整覆盖需求文档所列 128 项功能点。
2. 页面平均加载时间不超过 2 秒，核心接口响应时间不超过 500 毫秒。
3. 验收中发现缺陷的，乙方应在 5 个工作日内修复并重新提交验收。

第七条 质保期
1. 质保期为系统验收通过之日起 12 个月。
2. 质保期内乙方应提供 7×24 小时故障响应，重大故障 4 小时内到场处理。

第五章 违约责任

第八条 违约责任
1. 乙方逾期交付的，每逾期一日按合同总价款的 0.5% 向甲方支付违约金，累计不超过合同总价款的 20%。
2. 甲方逾期付款的，每逾期一日按应付未付金额的 0.3% 支付违约金。
3. 因一方违约给对方造成损失的，违约方应赔偿因此产生的直接经济损失。

第六章 保密与数据安全

第九条 保密义务
1. 双方对在履行本合同过程中知悉的对方商业秘密承担保密义务，保密期限为合同终止后五年。
2. 涉及个人信息处理的，双方应遵守《中华人民共和国个人信息保护法》的相关规定。
3. 合同终止后，乙方应在 30 日内删除或返还全部甲方数据，并出具书面删除证明。

第七章 争议解决

第十条 争议解决
1. 因本合同引起的争议，双方应友好协商解决。
2. 协商不成的，任何一方均可向甲方所在地有管辖权的人民法院提起诉讼。

第十一条 其他
1. 本合同自双方盖章之日起生效，一式肆份，双方各执贰份，具有同等法律效力。
2. 本合同未尽事宜，双方可另行签订补充协议，补充协议与本合同具有同等效力。

甲方（盖章）：星澜科技有限公司
授权代表：____________
签署日期：2026 年 9 月 10 日

乙方（盖章）：云舟数字技术有限公司
授权代表：____________
签署日期：2026 年 9 月 10 日`
