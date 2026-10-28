"""
中国劳动法条文知识库.

收录 14 部现行劳动法律法规的**完整条文** (政府官网公开文本)，用于 RAG 语义检索:
《劳动合同法》(2012修正) 《劳动法》(2018修正) 《社会保险法》(2018修正)
《劳动争议调解仲裁法》《就业促进法》(2015修正) 《劳动争议司法解释二》(法释〔2025〕12号)
《劳动合同法实施条例》《职工带薪年休假条例》《女职工劳动保护特别规定》
《工伤保险条例》(2010修订) 《劳动保障监察条例》《工资支付暂行规定》
《最低工资规定》《国务院关于职工工作时间的规定》

完整条文存放于 data/*.json，每条包含:
- law_name: 法律名称
- article: 条文编号
- content: 条文原文
- keywords: 关键词标签 (辅助检索)
- category: 关联的风险分类
- source: 政府公开文本来源

扩展条文 (民法典 / 个人信息保护法 / 医疗期 / 劳务派遣等)
见 ``app.rag.law_corpus_ext``，与本模块合并后构成完整语料。

数据来源: gov.cn / npc.gov.cn / court.gov.cn / mohrss.gov.cn 公开现行文本。
本模块内保留各法核心条文列表，仅在 JSON 文件缺失时降级使用。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.rag.law_corpus_ext import EXTENDED_RULES


# ── 《中华人民共和国劳动合同法》(2012修正) ────────────────────

LABOR_CONTRACT_LAW: list[dict] = [
    # 竞业限制
    {
        "law_name": "劳动合同法",
        "article": "第二十三条",
        "content": "用人单位与劳动者可以在劳动合同中约定保守用人单位的商业秘密和与知识产权相关的保密事项。对负有保密义务的劳动者，用人单位可以在劳动合同或者保密协议中与劳动者约定竞业限制条款，并约定在解除或者终止劳动合同后，在竞业限制期限内按月给予劳动者经济补偿。劳动者违反竞业限制约定的，应当按照约定向用人单位支付违约金。",
        "keywords": ["竞业限制", "保密协议", "竞业补偿金", "违约金", "商业秘密"],
        "category": "non_compete",
    },
    {
        "law_name": "劳动合同法",
        "article": "第二十四条",
        "content": "竞业限制的人员限于用人单位的高级管理人员、高级技术人员和其他负有保密义务的人员。竞业限制的范围、地域、期限由用人单位与劳动者约定，竞业限制的约定不得违反法律、法规的规定。在解除或者终止劳动合同后，前款规定的人员到与本单位生产或者经营同类产品、从事同类业务的有竞争关系的其他用人单位，或者自己开业生产或者经营同类产品、从事同类业务的竞业限制期限，不得超过二年。",
        "keywords": ["竞业限制", "二年", "期限", "高级管理人员", "高级技术人员"],
        "category": "non_compete",
    },
    # 试用期
    {
        "law_name": "劳动合同法",
        "article": "第十九条",
        "content": "劳动合同期限三个月以上不满一年的，试用期不得超过一个月；劳动合同期限一年以上不满三年的，试用期不得超过二个月；三年以上固定期限和无固定期限的劳动合同，试用期不得超过六个月。同一用人单位与同一劳动者只能约定一次试用期。以完成一定工作任务为期限的劳动合同或者劳动合同期限不满三个月的，不得约定试用期。试用期包含在劳动合同期限内。劳动合同仅约定试用期的，试用期不成立，该期限为劳动合同期限。",
        "keywords": ["试用期", "一个月", "二个月", "六个月", "试用期期限"],
        "category": "probation_salary",
    },
    {
        "law_name": "劳动合同法",
        "article": "第二十条",
        "content": "劳动者在试用期的工资不得低于本单位相同岗位最低档工资或者劳动合同约定工资的百分之八十，并不得低于用人单位所在地的最低工资标准。",
        "keywords": ["试用期工资", "百分之八十", "80%", "最低工资"],
        "category": "probation_salary",
    },
    # 试用期社保
    {
        "law_name": "劳动合同法",
        "article": "第十七条",
        "content": "劳动合同应当具备以下条款：（一）用人单位的名称、住所和法定代表人或者主要负责人；（二）劳动者的姓名、住址和居民身份证或者其他有效身份证件号码；（三）劳动合同期限；（四）工作内容和工作地点；（五）工作时间和休息休假；（六）劳动报酬；（七）社会保险；（八）劳动保护、劳动条件和职业危害防护；（九）法律、法规规定应当纳入劳动合同的其他事项。",
        "keywords": ["社会保险", "劳动合同必备条款", "劳动报酬", "工作时间"],
        "category": "probation_insurance",
    },
    # 扣薪/罚款
    {
        "law_name": "劳动合同法",
        "article": "第二十二条",
        "content": "用人单位为劳动者提供专项培训费用，对其进行专业技术培训的，可以与该劳动者订立协议，约定服务期。劳动者违反服务期约定的，应当按照约定向用人单位支付违约金。违约金的数额不得超过用人单位提供的培训费用。用人单位要求劳动者支付的违约金不得超过服务期尚未履行部分所应分摊的培训费用。",
        "keywords": ["培训费用", "服务期", "违约金", "专业技术培训", "分摊"],
        "category": "training_bond",
    },
    {
        "law_name": "劳动合同法",
        "article": "第二十五条",
        "content": "除本法第二十二条和第二十三条规定的情形外，用人单位不得与劳动者约定由劳动者承担违约金。",
        "keywords": ["违约金", "禁止约定", "培训服务期", "竞业限制"],
        "category": "salary_deduction",
    },
    # 岗位职责
    {
        "law_name": "劳动合同法",
        "article": "第三十五条",
        "content": "用人单位与劳动者协商一致，可以变更劳动合同约定的内容。变更劳动合同，应当采用书面形式。变更后的劳动合同文本由用人单位和劳动者各执一份。",
        "keywords": ["变更劳动合同", "协商一致", "岗位调整", "书面形式"],
        "category": "job_description",
    },
    # 无条件服从/调岗
    {
        "law_name": "劳动合同法",
        "article": "第四十条",
        "content": "有下列情形之一的，用人单位提前三十日以书面形式通知劳动者本人或者额外支付劳动者一个月工资后，可以解除劳动合同：（一）劳动者患病或者非因工负伤，在规定的医疗期满后不能从事原工作，也不能从事由用人单位另行安排的工作的；（二）劳动者不能胜任工作，经过培训或者调整工作岗位，仍不能胜任工作的；（三）劳动合同订立时所依据的客观情况发生重大变化，致使劳动合同无法履行，经用人单位与劳动者协商，未能就变更劳动合同内容达成协议的。",
        "keywords": ["调岗", "不能胜任", "解除劳动合同", "三十日通知", "医疗期"],
        "category": "obedience_clause",
    },
    # 离职
    {
        "law_name": "劳动合同法",
        "article": "第三十七条",
        "content": "劳动者提前三十日以书面形式通知用人单位，可以解除劳动合同。劳动者在试用期内提前三日通知用人单位，可以解除劳动合同。",
        "keywords": ["辞职", "三十日", "提前通知", "试用期三日", "解除劳动合同"],
        "category": "resignation",
    },
    {
        "law_name": "劳动合同法",
        "article": "第三十八条",
        "content": "用人单位有下列情形之一的，劳动者可以解除劳动合同：（一）未按照劳动合同约定提供劳动保护或者劳动条件的；（二）未及时足额支付劳动报酬的；（三）未依法为劳动者缴纳社会保险费的；（四）用人单位的规章制度违反法律、法规的规定，损害劳动者权益的；（五）因本法第二十六条第一款规定的情形致使劳动合同无效的；（六）法律、行政法规规定劳动者可以解除劳动合同的其他情形。",
        "keywords": ["被迫辞职", "未缴纳社保", "未支付报酬", "劳动保护", "即时解除"],
        "category": "resignation",
    },
    # 休假
    {
        "law_name": "劳动合同法",
        "article": "第三十一条",
        "content": "用人单位应当严格执行劳动定额标准，不得强迫或者变相强迫劳动者加班。用人单位安排加班的，应当按照国家有关规定向劳动者支付加班费。",
        "keywords": ["加班", "加班费", "强迫加班", "劳动定额"],
        "category": "leave_rights",
    },
    # 争议管辖
    {
        "law_name": "劳动合同法",
        "article": "第七十七条",
        "content": "劳动者合法权益受到侵害的，有权要求有关部门依法处理，或者依法申请仲裁、提起诉讼。",
        "keywords": ["劳动仲裁", "诉讼", "争议解决", "合法权益"],
        "category": "jurisdiction",
    },
    # 经济补偿
    {
        "law_name": "劳动合同法",
        "article": "第四十六条",
        "content": "有下列情形之一的，用人单位应当向劳动者支付经济补偿：（一）劳动者依照本法第三十八条规定解除劳动合同的；（二）用人单位依照本法第三十六条规定向劳动者提出解除劳动合同并与劳动者协商一致解除劳动合同的；（三）用人单位依照本法第四十条规定解除劳动合同的；（四）用人单位依照本法第四十一条第一款规定解除劳动合同的；（五）除用人单位维持或者提高劳动合同约定条件续订劳动合同，劳动者不同意续订的情形外，依照本法第四十四条第一项规定终止固定期限劳动合同的；（六）依照本法第四十四条第四项、第五项规定终止劳动合同的；（七）法律、行政法规规定的其他情形。",
        "keywords": ["经济补偿", "N+1", "解除合同补偿", "终止合同"],
        "category": "resignation",
    },
    {
        "law_name": "劳动合同法",
        "article": "第四十七条",
        "content": "经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资的标准向劳动者支付。六个月以上不满一年的，按一年计算；不满六个月的，向劳动者支付半个月工资的经济补偿。劳动者月工资高于用人单位所在直辖市、设区的市级人民政府公布的本地区上年度职工月平均工资三倍的，向其支付经济补偿的标准按职工月平均工资三倍的数额支付，向其支付经济补偿的年限最高不超过十二年。本条所称月工资是指劳动者在劳动合同解除或者终止前十二个月的平均工资。",
        "keywords": ["经济补偿计算", "N+1", "月工资", "三倍封顶", "十二年上限"],
        "category": "resignation",
    },
    # 违法解除
    {
        "law_name": "劳动合同法",
        "article": "第四十八条",
        "content": "用人单位违反本法规定解除或者终止劳动合同，劳动者要求继续履行劳动合同的，用人单位应当继续履行；劳动者不要求继续履行劳动合同或者劳动合同已经不能继续履行的，用人单位应当依照本法第八十七条规定支付赔偿金。",
        "keywords": ["违法解除", "继续履行", "赔偿金", "2N"],
        "category": "resignation",
    },
    {
        "law_name": "劳动合同法",
        "article": "第八十七条",
        "content": "用人单位违反本法规定解除或者终止劳动合同的，应当依照本法第四十七条规定的经济补偿标准的二倍向劳动者支付赔偿金。",
        "keywords": ["2N赔偿", "违法解除赔偿", "双倍经济补偿"],
        "category": "resignation",
    },
]

# ── 《中华人民共和国劳动法》 ──────────────────────────────────

LABOR_LAW: list[dict] = [
    {
        "law_name": "劳动法",
        "article": "第三十六条",
        "content": "国家实行劳动者每日工作时间不超过八小时、平均每周工作时间不超过四十四小时的工时制度。",
        "keywords": ["工作时间", "八小时", "四十四小时", "工时制度"],
        "category": "leave_rights",
    },
    {
        "law_name": "劳动法",
        "article": "第四十一条",
        "content": "用人单位由于生产经营需要，经与工会和劳动者协商后可以延长工作时间，一般每日不得超过一小时；因特殊原因需要延长工作时间的，在保障劳动者身体健康的条件下延长工作时间每日不得超过三小时，但是每月不得超过三十六小时。",
        "keywords": ["加班时间", "每月36小时", "延长工作时间", "加班上限"],
        "category": "leave_rights",
    },
    {
        "law_name": "劳动法",
        "article": "第四十四条",
        "content": "有下列情形之一的，用人单位应当按照下列标准支付高于劳动者正常工作时间工资的工资报酬：（一）安排劳动者延长工作时间的，支付不低于工资的百分之一百五十的工资报酬；（二）休息日安排劳动者工作又不能安排补休的，支付不低于工资的百分之二百的工资报酬；（三）法定休假日安排劳动者工作的，支付不低于工资的百分之三百的工资报酬。",
        "keywords": ["加班费", "1.5倍", "2倍", "3倍", "法定假日", "休息日"],
        "category": "leave_rights",
    },
    {
        "law_name": "劳动法",
        "article": "第四十五条",
        "content": "国家实行带薪年休假制度。劳动者连续工作一年以上的，享受带薪年休假。具体办法由国务院规定。",
        "keywords": ["年休假", "带薪休假", "连续工作一年"],
        "category": "leave_rights",
    },
    {
        "law_name": "劳动法",
        "article": "第五十条",
        "content": "工资应当以货币形式按月支付给劳动者本人。不得克扣或者无故拖欠劳动者的工资。",
        "keywords": ["工资支付", "按月支付", "克扣工资", "拖欠工资"],
        "category": "salary_deduction",
    },
    {
        "law_name": "劳动法",
        "article": "第七十二条",
        "content": "社会保险基金按照保险类型确定资金来源，逐步实行社会统筹。用人单位和劳动者必须依法参加社会保险，缴纳社会保险费。",
        "keywords": ["社会保险", "必须参加", "缴纳社保", "强制社保"],
        "category": "probation_insurance",
    },
    {
        "law_name": "劳动法",
        "article": "第七十九条",
        "content": "劳动争议发生后，当事人可以向本单位劳动争议调解委员会申请调解；调解不成，当事人一方要求仲裁的，可以向劳动争议仲裁委员会申请仲裁。当事人一方也可以直接向劳动争议仲裁委员会申请仲裁。对仲裁裁决不服的，可以向人民法院提起诉讼。",
        "keywords": ["劳动仲裁", "调解", "仲裁前置", "诉讼"],
        "category": "jurisdiction",
    },
]

# ── 《中华人民共和国社会保险法》 ────────────────────────────────

SOCIAL_INSURANCE_LAW: list[dict] = [
    {
        "law_name": "社会保险法",
        "article": "第五十八条",
        "content": "用人单位应当自用工之日起三十日内为其职工向社会保险经办机构申请办理社会保险登记。未办理社会保险登记的，由社会保险经办机构核定其应当缴纳的社会保险费。",
        "keywords": ["用工之日起", "三十日内", "社保登记", "入职即缴社保"],
        "category": "probation_insurance",
    },
    {
        "law_name": "社会保险法",
        "article": "第六十条",
        "content": "用人单位应当自行申报、按时足额缴纳社会保险费，非因不可抗力等法定事由不得缓缴、减免。职工应当缴纳的社会保险费由用人单位代扣代缴，用人单位应当按月将缴纳社会保险费的明细情况告知本人。",
        "keywords": ["足额缴纳", "按时缴纳", "代扣代缴", "社保不得减免"],
        "category": "probation_insurance",
    },
]

# ── 《劳动争议调解仲裁法》 ──────────────────────────────────────

ARBITRATION_LAW: list[dict] = [
    {
        "law_name": "劳动争议调解仲裁法",
        "article": "第二十一条",
        "content": "劳动争议仲裁委员会负责管辖本区域内发生的劳动争议。劳动争议由劳动合同履行地或者用人单位所在地的劳动争议仲裁委员会管辖。双方当事人分别向劳动合同履行地和用人单位所在地的劳动争议仲裁委员会申请仲裁的，由劳动合同履行地的劳动争议仲裁委员会管辖。",
        "keywords": ["仲裁管辖", "劳动合同履行地", "用人单位所在地", "管辖权"],
        "category": "jurisdiction",
    },
]

# ── 《职工带薪年休假条例》 ──────────────────────────────────────

ANNUAL_LEAVE: list[dict] = [
    {
        "law_name": "职工带薪年休假条例",
        "article": "第三条",
        "content": "职工累计工作已满1年不满10年的，年休假5天；已满10年不满20年的，年休假10天；已满20年的，年休假15天。国家法定休假日、休息日不计入年休假的假期。",
        "keywords": ["年休假天数", "5天", "10天", "15天", "累计工龄"],
        "category": "leave_rights",
    },
    {
        "law_name": "职工带薪年休假条例",
        "article": "第五条",
        "content": "单位确因工作需要不能安排职工休年休假的，经职工本人同意，可以不安排职工休年休假。对职工应休未休的年休假天数，单位应当按照该职工日工资收入的300%支付年休假工资报酬。",
        "keywords": ["未休年假补偿", "300%工资", "年假折算"],
        "category": "leave_rights",
    },
]

# ── 合同审查常用配套法规（重点条款）────────────────────────────
# 来源：国务院、人力资源社会保障部门公开现行文本。完整劳动合同法见 data/。
SUPPLEMENTARY_LABOR_RULES: list[dict] = [
    {"law_name": "劳动合同法实施条例", "article": "第五条", "content": "自用工之日起一个月内，经用人单位书面通知后，劳动者不与用人单位订立书面劳动合同的，用人单位应当书面通知劳动者终止劳动关系，无需向劳动者支付经济补偿，但是应当依法向劳动者支付其实际工作时间的劳动报酬。", "keywords": ["书面劳动合同", "一个月", "终止劳动关系"], "category": "job_description"},
    {"law_name": "劳动合同法实施条例", "article": "第六条", "content": "用人单位自用工之日起超过一个月不满一年未与劳动者订立书面劳动合同的，应当依照劳动合同法第八十二条的规定向劳动者每月支付两倍的工资，并与劳动者补订书面劳动合同。", "keywords": ["未签合同", "双倍工资", "补订合同"], "category": "salary_deduction"},
    {"law_name": "劳动合同法实施条例", "article": "第二十一条", "content": "劳动者达到法定退休年龄的，劳动合同终止。", "keywords": ["退休年龄", "劳动合同终止"], "category": "resignation"},
    {"law_name": "工资支付暂行规定", "article": "第六条", "content": "用人单位应将工资支付给劳动者本人。劳动者本人因故不能领取工资时，可由其亲属或委托他人代领。用人单位可委托银行代发工资。", "keywords": ["工资支付", "本人领取", "银行代发"], "category": "salary_deduction"},
    {"law_name": "工资支付暂行规定", "article": "第七条", "content": "工资必须在用人单位与劳动者约定的日期支付。如遇节假日或休息日，则应提前在最近的工作日支付。工资至少每月支付一次。", "keywords": ["发薪日", "按月支付", "工资"], "category": "salary_deduction"},
    {"law_name": "工资支付暂行规定", "article": "第九条", "content": "劳动关系双方依法解除或终止劳动合同时，用人单位应在解除或终止劳动合同时一次付清劳动者工资。", "keywords": ["离职", "结清工资", "终止合同"], "category": "resignation"},
    {"law_name": "最低工资规定", "article": "第十二条", "content": "在劳动者提供正常劳动的情况下，用人单位应支付给劳动者的工资在剔除下列各项以后，不得低于当地最低工资标准：延长工作时间工资；中班、夜班、高温、低温、井下、有毒有害等特殊工作环境、条件下的津贴；法律、法规和国家规定的劳动者福利待遇等。", "keywords": ["最低工资", "加班费", "津贴"], "category": "probation_salary"},
    {"law_name": "女职工劳动保护特别规定", "article": "第五条", "content": "用人单位不得因女职工怀孕、生育、哺乳降低其工资、予以辞退、与其解除劳动或者聘用合同。", "keywords": ["怀孕", "生育", "哺乳", "不得辞退"], "category": "resignation"},
    {"law_name": "女职工劳动保护特别规定", "article": "第七条", "content": "女职工生育享受98天产假，其中产前可以休假15天；难产的，应增加产假15天；生育多胞胎的，每多生育1个婴儿，可增加产假15天。", "keywords": ["产假", "98天", "难产"], "category": "leave_rights"},
    {"law_name": "女职工劳动保护特别规定", "article": "第九条", "content": "对哺乳未满1周岁婴儿的女职工，用人单位不得延长劳动时间或者安排夜班劳动。用人单位应当在每天的劳动时间内为哺乳期女职工安排1小时哺乳时间。", "keywords": ["哺乳期", "夜班", "哺乳时间"], "category": "leave_rights"},
    {"law_name": "工伤保险条例", "article": "第十四条", "content": "职工有下列情形之一的，应当认定为工伤：在工作时间和工作场所内，因工作原因受到事故伤害的；工作时间前后在工作场所内，从事与工作有关的预备性或者收尾性工作受到事故伤害的；在工作时间和工作场所内，因履行工作职责受到暴力等意外伤害的等。", "keywords": ["工伤认定", "工作时间", "工作场所"], "category": "general"},
    {"law_name": "工伤保险条例", "article": "第十七条", "content": "职工发生事故伤害或者按照职业病防治法规定被诊断、鉴定为职业病，所在单位应当自事故伤害发生之日或者被诊断、鉴定为职业病之日起30日内，向统筹地区社会保险行政部门提出工伤认定申请。", "keywords": ["工伤认定申请", "30日", "职业病"], "category": "general"},
    {"law_name": "劳动保障监察条例", "article": "第九条", "content": "任何组织或者个人对违反劳动保障法律、法规或者规章的行为，有权向劳动保障行政部门举报。劳动者认为用人单位侵犯其劳动保障合法权益的，有权向劳动保障行政部门投诉。", "keywords": ["劳动监察", "投诉", "举报"], "category": "jurisdiction"},
    {"law_name": "劳动保障监察条例", "article": "第二十条", "content": "违反劳动保障法律、法规或者规章的行为在2年内未被劳动保障行政部门发现，也未被举报、投诉的，劳动保障行政部门不再查处。前款规定的期限，自违反劳动保障法律、法规或者规章的行为发生之日起计算；违反行为有连续或者继续状态的，自行为终了之日起计算。", "keywords": ["劳动监察", "两年", "投诉时效"], "category": "jurisdiction"},
    {"law_name": "国务院关于职工工作时间的规定", "article": "第三条", "content": "职工每日工作8小时、每周工作40小时。", "keywords": ["八小时", "四十小时", "工时"], "category": "leave_rights"},
    {"law_name": "职工带薪年休假条例", "article": "第二条", "content": "机关、团体、企业、事业单位、民办非企业单位、有雇工的个体工商户等单位的职工连续工作1年以上的，享受带薪年休假。", "keywords": ["带薪年休假", "连续工作一年"], "category": "leave_rights"},
]

# ── 汇总所有法条 ───────────────────────────────────────────────

#: 完整条文 JSON (data/ 目录) 与文件缺失时的核心条款降级列表
_FULL_CORPUS_FILES: list[str] = [
    "labor_contract_law_2012.json",
    "labor_law_2018.json",
    "social_insurance_law_2018.json",
    "arbitration_law_2007.json",
    "employment_promotion_law_2015.json",
    "judicial_interpretation_labor_2025.json",
    "labor_contract_law_impl_regulation.json",
    "annual_paid_leave_regulation.json",
    "female_employee_protection_regulation.json",
    "work_injury_insurance_regulation.json",
    "labor_security_supervision_regulation.json",
    "wage_payment_provisional_regulation.json",
    "minimum_wage_regulation.json",
    "working_hours_regulation.json",
]

_FALLBACK_LAWS: list[list[dict]] = [
    LABOR_CONTRACT_LAW,
    LABOR_LAW,
    SOCIAL_INSURANCE_LAW,
    ARBITRATION_LAW,
    ANNUAL_LEAVE,
    SUPPLEMENTARY_LABOR_RULES,
]


def _load_full_corpus() -> list[dict]:
    """加载 data/ 下全部完整条文; 文件缺失的法律回退到内置核心条款; 并入扩展条文."""
    data_dir = Path(__file__).with_name("data")
    laws: list[dict] = []
    loaded_names: set[str] = set()
    for fname in _FULL_CORPUS_FILES:
        try:
            rows = json.loads((data_dir / fname).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list) or not rows:
            continue
        loaded_names.update(row["law_name"] for row in rows)
        laws.extend(rows)
    for fallback in _FALLBACK_LAWS:
        for row in fallback:
            if row["law_name"] not in loaded_names:
                laws.append(row)
    # 扩展条文 (民法典/个人信息保护法/医疗期/劳务派遣等); 与完整条文重复的条目在下方统一去重
    laws.extend(EXTENDED_RULES)
    # 按 (law_name, article) 去重, 保留首次出现
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for law in laws:
        key = (law["law_name"], law["article"])
        if key not in seen:
            seen.add(key)
            unique.append(law)
    return unique


ALL_LAWS: list[dict] = _load_full_corpus()


def corpus_hash() -> str:
    """语料内容签名 (sha256 前 12 位), 用于判断索引是否需要重建."""
    payload = json.dumps(ALL_LAWS, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
