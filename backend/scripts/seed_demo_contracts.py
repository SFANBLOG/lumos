"""写入 100 份可重复执行的 Lumos 演示合同数据。

执行方式（Docker）：docker compose exec backend python scripts/seed_demo_contracts.py
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select

from app.core.database import async_session_factory, engine
from app.models.analysis import AnalysisResult, RiskCategory, RiskItem, RiskLevel
from app.models.contract import Contract, ContractSource, ContractStatus


CATEGORIES = [
    ("劳动合同", "员工与公司就岗位、薪酬、工时、社保和保密义务达成如下约定。"),
    ("保密协议", "双方对业务计划、技术资料、客户信息和交易条件承担保密义务。"),
    ("采购框架协议", "供应商应按订单交付产品，并满足验收、质量和售后服务要求。"),
    ("销售合同", "甲方向乙方销售产品，乙方按约定账期支付货款并完成验收。"),
    ("软件许可协议", "许可方授予被许可方在约定地域和期限内使用软件的权利。"),
    ("数据处理协议", "处理方仅按委托方书面指令处理个人信息，并采取安全措施。"),
    ("市场推广服务协议", "服务方负责推广活动策划、投放执行和效果数据交付。"),
    ("房屋租赁合同", "出租方将房屋出租给承租方，租期、租金及维修责任按本合同执行。"),
    ("技术开发合同", "受托方完成系统开发、测试、交付和知识产权移交工作。"),
    ("咨询服务协议", "顾问为客户提供业务咨询、研究分析和阶段性成果报告。"),
]

RISK_DATA = [
    (RiskCategory.NON_COMPETE, "竞业限制范围过宽", "竞业限制未限定竞争业务范围或补偿标准。", RiskLevel.HIGH, 42),
    (RiskCategory.PROBATION_SALARY, "试用期薪酬约定需复核", "试用期工资表述可能低于法定或约定标准。", RiskLevel.MEDIUM, 68),
    (RiskCategory.SALARY_DEDUCTION, "违约扣款表述不明确", "以笼统扣款替代损失核算，存在争议风险。", RiskLevel.MEDIUM, 65),
    (RiskCategory.JURISDICTION, "争议管辖条款待确认", "约定的争议解决地可能增加维权成本。", RiskLevel.LOW, 82),
    (RiskCategory.LEAVE_RIGHTS, "权利保障条款完整", "未发现明显损害法定休假权益的表述。", RiskLevel.SAFE, 94),
]


async def seed() -> None:
    created = 0
    try:
        async with async_session_factory() as session:
            for index in range(100):
                marker = f"lumos-demo-contract-v1-{index:03d}"
                exists = (await session.execute(select(Contract.id).where(Contract.device_id == marker))).first()
                if exists:
                    continue

                category, body = CATEGORIES[index % len(CATEGORIES)]
                status = ContractStatus.COMPLETED if index < 84 else (ContractStatus.ANALYZING if index < 92 else ContractStatus.PENDING)
                created_at = datetime.now(UTC) - timedelta(days=index // 3, hours=(index * 3) % 24)
                text = (
                f"{category}（演示数据 {index + 1:03d}）\n"
                f"甲方：华东企业服务有限公司；乙方：合作方{index + 1:03d}号。\n{body}\n"
                f"合同金额：{(index % 12 + 1) * 5}万元；期限：2026年1月1日至2026年12月31日。\n"
                "双方应遵循适用法律法规，重大变更须经书面确认。本数据仅用于产品演示。"
                )
                contract = Contract(
                raw_text=text,
                source=list(ContractSource)[index % len(ContractSource)],
                status=status,
                page_count=2 + index % 18,
                char_count=len(text),
                device_id=marker,
                created_at=created_at,
                updated_at=created_at,
                )
                session.add(contract)
                await session.flush()

                if status == ContractStatus.COMPLETED:
                    risk_category, title, explanation, level, score = RISK_DATA[index % len(RISK_DATA)]
                    result = AnalysisResult(
                    contract_id=contract.id,
                    overall_score=score,
                    overall_level=level,
                    summary=f"{category}演示审查完成：{title}。",
                    created_at=created_at + timedelta(minutes=3),
                    )
                    session.add(result)
                    await session.flush()
                    session.add(RiskItem(
                    analysis_id=result.id,
                    category=risk_category,
                    level=level,
                    title=title,
                    original_clause=body,
                    explanation=explanation,
                    legal_basis="演示数据：需结合合同适用法律及企业审查标准确认。",
                    negotiation_tip="建议明确责任边界、适用条件与可执行的补救机制。",
                    score=score,
                    order=1,
                    ))
                created += 1
            await session.commit()
            total = (await session.execute(select(func.count()).select_from(Contract))).scalar_one()
    finally:
        await engine.dispose()
    print(f"演示合同写入完成：新增 {created} 份；当前合同总数 {total}；重复执行不会重复创建。")


if __name__ == "__main__":
    asyncio.run(seed())
