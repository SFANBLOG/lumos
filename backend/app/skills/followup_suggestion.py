"""
技能: 追问建议生成.

根据风险分类 (或为空) 给出劳动者视角的追问语料, 供智能咨询界面作快捷提问。
"""

from __future__ import annotations

from app.models.analysis import RiskCategory
from app.skills.base import BaseSkill

# 按坑点分类预置追问语料 (面向劳动者)
_FOLLOWUPS: dict[RiskCategory, list[str]] = {
    RiskCategory.NON_COMPETE: [
        "竞业限制补偿金低于离职前12个月平均工资的30%，能拒绝履行吗？",
        "竞业限制适用高管/高技/保密义务人吗？期限有没有超过2年？",
    ],
    RiskCategory.PROBATION_SALARY: [
        "试用期工资低于转正工资的80%，合法吗？",
        "试用期工资低于当地最低工资标准怎么办？",
    ],
    RiskCategory.PROBATION_INSURANCE: [
        "试用期不缴社保，可以要求补缴吗？",
    ],
    RiskCategory.SALARY_DEDUCTION: [
        "公司扣我工资，什么情况才合法？",
        "工资拖欠不发，多久算违法？",
    ],
    RiskCategory.JOB_DESCRIPTION: [
        "岗位职责写得很模糊，后面被调岗能拒绝吗？",
        "考核标准不明确就扣绩效，有依据吗？",
    ],
    RiskCategory.OBEDIENCE_CLAUSE: [
        "条款约定『无条件服从安排』，包含无限加班和随意调岗吗？",
    ],
    RiskCategory.RESIGNATION: [
        "离职必须领导审批才能走吗？提前30天书面通知就行吗？",
        "公司拖着不批离职，工资怎么办？",
    ],
    RiskCategory.LEAVE_RIGHTS: [
        "年假/婚假/产假被变相取消，能主张什么？",
    ],
    RiskCategory.JURISDICTION: [
        "合同约定异地仲裁/法院管辖，我维权会吃亏吗？",
    ],
    RiskCategory.TRAINING_BOND: [
        "服务期违约金超过培训费，超出的部分要付吗？",
        "什么才算『专项培训费用』？普通入职培训算吗？",
    ],
    RiskCategory.UNLAWFUL_TERMINATION: [
        "公司辞退我但没给赔偿金，违法解除能主张2N吗？",
        "被以『不胜任工作』辞退，公司走完调岗或培训程序了吗？",
    ],
    RiskCategory.SEVERANCE_PAY: [
        "经济补偿金按什么基数算？包含奖金和补贴吗？",
        "公司说只给一个月补偿，工作3年应该怎么算？",
    ],
    RiskCategory.NO_WRITTEN_CONTRACT: [
        "入职半年了还没签书面合同，能主张二倍工资吗？",
        "没签合同怎么证明劳动关系？工资流水和考勤算证据吗？",
    ],
    RiskCategory.OVERTIME_PAY: [
        "加班费按基本工资算还是按全额工资算？",
        "公司用『调休』代替加班费，休息日加班可以这样吗？",
    ],
    RiskCategory.ILLEGAL_PENALTY: [
        "合同里约定我提前离职要付违约金，这条有效吗？",
        "除服务期和竞业限制外，还有哪些违约金是违法的？",
    ],
    RiskCategory.DEPOSIT_GUARANTEE: [
        "入职要交押金或扣押毕业证，公司这样做违法吗？",
        "离职时公司扣着档案不给转，我该怎么维权？",
    ],
}

_FALLBACK: list[str] = [
    "公司这个做法有法律依据吗？",
    "我现在应该保留哪些证据？",
]


class FollowupSuggestionSkill(BaseSkill):
    """根据风险分类生成追问建议语料."""

    name = "followup_suggestion"
    description = "根据风险分类生成追问建议语料"

    async def execute(
        self,
        *,
        categories: list[str] | None = None,
        **kwargs: object,
    ) -> dict:
        seen: set[str] = set()
        suggestions: list[str] = []
        for raw in categories or []:
            try:
                cat = RiskCategory(raw)
            except ValueError:
                continue
            for q in _FOLLOWUPS.get(cat, []):
                if q not in seen:
                    seen.add(q)
                    suggestions.append(q)
        for q in _FALLBACK:
            if q not in seen:
                seen.add(q)
                suggestions.append(q)
        return {"suggestions": suggestions[:4]}
