"""条款级修改建议 (redline) 规则库.

市面合同审查产品的核心交付物是「这一条改成什么文本」，而本项目原先只有
`negotiation_tip`（对 HR 说什么）。本模块按风险类别提供可直接复制的替代措辞，
作为确定性兜底: LLM 未给出建议时也能保证每条风险都有 redline，不依赖模型可用性。

后续若要升级为「逐条按原文生成改写」，只需把 `build_revision` 换成 LLM 实现，
调用方与落库字段都无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.analysis import RiskCategory


@dataclass(frozen=True)
class RedlineRule:
    """一条替代措辞建议."""

    suggested: str
    reason: str
    legal_basis: str


REDLINE_LIBRARY: dict[str, RedlineRule] = {
    RiskCategory.NON_COMPETE.value: RedlineRule(
        suggested=(
            "竞业限制期限自解除或终止劳动合同之日起不超过二年，范围限于与甲方"
            "存在竞争关系的同类业务；甲方应在竞业限制期内按月向乙方支付经济补偿"
            "（建议不低于乙方离职前十二个月平均工资的 30%，且不低于当地最低工资标准）；"
            "乙方违约金应与甲方实际损失相当，双方另行约定上限。"
        ),
        reason="补偿过低、范围过宽或期限超二年的竞业条款存在被认定无效或显失公平的风险。",
        legal_basis="《中华人民共和国劳动合同法》第二十三条、第二十四条",
    ),
    RiskCategory.PROBATION_SALARY.value: RedlineRule(
        suggested=(
            "试用期工资不得低于本单位相同岗位最低档工资或者劳动合同约定工资的百分之八十，"
            "并不得低于用人单位所在地的最低工资标准。"
        ),
        reason="试用期工资低于法定下限属违法约定。",
        legal_basis="《中华人民共和国劳动合同法》第二十条",
    ),
    RiskCategory.PROBATION_INSURANCE.value: RedlineRule(
        suggested=(
            "甲方应自用工之日起三十日内为乙方办理社会保险登记并足额缴纳社会保险费，"
            "试用期同样适用，乙方不得被要求签署自愿放弃社保的声明。"
        ),
        reason="试用期不缴社保或约定「自愿放弃」均属无效。",
        legal_basis="《中华人民共和国社会保险法》第五十八条；《中华人民共和国劳动合同法》第三十八条",
    ),
    RiskCategory.SALARY_DEDUCTION.value: RedlineRule(
        suggested=(
            "甲方不得无故克扣乙方工资；因乙方原因造成经济损失需扣除工资的，"
            "每月扣除部分不得超过当月工资的 20%，且扣除后不得低于当地最低工资标准。"
        ),
        reason="笼统的「公司有权扣款/罚款」缺少法定依据与上限。",
        legal_basis="《工资支付暂行规定》第十六条",
    ),
    RiskCategory.JOB_DESCRIPTION.value: RedlineRule(
        suggested=(
            "乙方担任【具体岗位】，职责范围为【具体职责】；甲方调整乙方岗位、"
            "工作地点或薪酬标准，应与乙方协商一致并签订书面变更协议。"
        ),
        reason="「由公司根据经营需要安排」使单方调岗降薪缺少约束。",
        legal_basis="《中华人民共和国劳动合同法》第十七条、第三十五条",
    ),
    RiskCategory.OBEDIENCE_CLAUSE.value: RedlineRule(
        suggested=(
            "乙方应遵守甲方依法制定并已向乙方公示的规章制度；甲方安排工作任务时"
            "不得违反法律法规，不得要求乙方从事超出约定岗位范围且未经协商的工作。"
        ),
        reason="「无条件服从一切安排」排除劳动者主要权利，属无效格式条款。",
        legal_basis="《中华人民共和国劳动合同法》第二十六条；《中华人民共和国劳动法》第三十二条",
    ),
    RiskCategory.RESIGNATION.value: RedlineRule(
        suggested=(
            "乙方提前三十日（试用期内提前三日）以书面形式通知甲方，即可解除劳动合同，"
            "无需甲方批准；甲方应在解除时出具证明并在十五日内办理档案与社保转移。"
        ),
        reason="把「离职审批」设为解除前置条件违反劳动者的法定解除权。",
        legal_basis="《中华人民共和国劳动合同法》第三十七条、第五十条",
    ),
    RiskCategory.LEAVE_RIGHTS.value: RedlineRule(
        suggested=(
            "乙方依法享有法定节假日、休息日、带薪年休假、婚丧假、产假等假期；"
            "甲方安排加班应与乙方协商并依法支付加班费或安排补休。"
        ),
        reason="排除或限制法定休假权益的约定无效。",
        legal_basis="《中华人民共和国劳动法》第四十条至第四十五条；《职工带薪年休假条例》第二条",
    ),
    RiskCategory.JURISDICTION.value: RedlineRule(
        suggested=(
            "因本合同发生的劳动争议，由劳动合同履行地或者甲方所在地有管辖权的"
            "劳动争议仲裁委员会管辖；对仲裁裁决不服的，可依法向人民法院起诉。"
        ),
        reason="约定异地管辖会显著抬高劳动者的维权成本。",
        legal_basis="《中华人民共和国劳动争议调解仲裁法》第二十一条",
    ),
    RiskCategory.TRAINING_BOND.value: RedlineRule(
        suggested=(
            "甲方为乙方提供专项培训费用并进行专业技术培训的，可约定服务期；"
            "违约金数额不得超过甲方提供的培训费用，且不得超过服务期尚未履行部分"
            "所应分摊的培训费用。"
        ),
        reason="以任意金额违约金绑定服务期超出法定上限。",
        legal_basis="《中华人民共和国劳动合同法》第二十二条",
    ),
}

_GENERIC = RedlineRule(
    suggested="建议删除该表述或按法定标准重新约定，并在签署前由双方书面确认。",
    reason="该条款表述与劳动者法定权益存在冲突。",
    legal_basis="《中华人民共和国劳动合同法》第二十六条",
)


def build_revision(category: str) -> RedlineRule:
    """按风险类别取替代措辞; 未知分类回退到通用建议."""
    return REDLINE_LIBRARY.get(category, _GENERIC)


def attach_redlines(assessments: list) -> int:
    """为每条风险补齐 ``suggested_revision`` (已有内容不覆盖).

    Returns:
        本次实际补全的条数。
    """
    filled = 0
    for assessment in assessments:
        if getattr(assessment, "suggested_revision", ""):
            continue
        category = getattr(assessment, "category", None)
        key = getattr(category, "value", str(category or ""))
        assessment.suggested_revision = build_revision(key).suggested
        filled += 1
    return filled
