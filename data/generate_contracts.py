"""
生成 50 份差异化劳动合同样本.

用于测试 Lumos 合同风险分析系统的覆盖能力。
样本按风险等级分目录: low-risk / medium-risk / high-risk / mixed
"""

from __future__ import annotations

import random
from pathlib import Path

random.seed(42)

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "contracts"

COMPANY_NAMES = [
    "星辰科技有限公司",
    "蓝海创新股份有限公司",
    "云帆网络科技",
    "金盾劳务服务有限公司",
    "鼎盛人力资源集团",
    "华夏咨询管理有限公司",
    "鹏程物流有限公司",
    "启航教育科技",
    "瑞丰金融信息服务",
    "博远文化传媒",
]

POSITIONS = [
    "高级软件工程师",
    "产品经理",
    "市场专员",
    "人事主管",
    "财务分析师",
    "UI 设计师",
    "销售代表",
    "运营专员",
    "法务助理",
    "行政助理",
]

LOCATIONS = [
    "北京市朝阳区",
    "上海市浦东新区",
    "深圳市南山区",
    "广州市天河区",
    "杭州市西湖区",
    "成都市高新区",
    "武汉市东湖高新区",
    "南京市建邺区",
    "西安市雁塔区",
    "苏州市工业园区",
]


def clause_probation(risk: str) -> str:
    if risk == "low":
        salary = random.choice(["100%", "90%", "95%"])
        return f"试用期为 {random.randint(1,3)} 个月，试用期工资为转正工资的 {salary}，并依法缴纳社会保险。"
    if risk == "medium":
        return f"试用期为 {random.randint(1,3)} 个月，试用期工资为转正工资的 80%。"
    return f"试用期为 {random.randint(3,6)} 个月，试用期工资为转正工资的 70%，试用期不缴纳社保。"


def clause_salary(risk: str) -> str:
    if risk == "low":
        return "甲方每月 15 日前以货币形式足额支付乙方工资，不得无故克扣或拖欠。"
    if risk == "medium":
        return "甲方每月支付乙方工资，如因乙方失误造成公司损失，甲方可从工资中扣除相应赔偿。"
    return "甲方有权根据乙方工作表现、迟到早退等情况任意扣减乙方工资，无需事先通知。"


def clause_job(risk: str) -> str:
    if risk == "low":
        return "乙方岗位为 {{position}}，工作地点为 {{location}}，具体工作内容以岗位职责说明书为准。"
    return "乙方需服从甲方的一切合理安排，甲方有权根据经营需要随时调整乙方的工作岗位和工作地点，乙方不得拒绝。"


def clause_resignation(risk: str) -> str:
    if risk == "low":
        return "乙方提前三十日以书面形式通知甲方，可以解除劳动合同。"
    if risk == "medium":
        return "乙方辞职需经甲方批准，未经批准擅自离职的，需赔偿甲方一个月工资。"
    return "乙方在服务期内不得提出辞职，否则需向甲方支付违约金人民币 10 万元。"


def clause_noncompete(risk: str) -> str:
    if risk in ("low", "medium"):
        return ""
    return (
        "乙方在职期间及离职后三年内，不得从事与甲方业务相同或相近的工作，"
        "否则需支付违约金。甲方每月支付竞业限制补偿金人民币 500 元。"
    )


def clause_jurisdiction(risk: str) -> str:
    if risk == "low":
        return "因履行本合同发生争议，双方可向劳动合同履行地劳动争议仲裁委员会申请仲裁。"
    return "因履行本合同发生争议，双方同意由甲方所在地劳动争议仲裁委员会仲裁。"


def clause_leave(risk: str) -> str:
    if risk == "low":
        return "乙方依法享有法定节假日、年休假、病假、婚假、产假等假期。"
    if risk == "medium":
        return "乙方工作满一年后享有 3 天年假。"
    return "乙方工作期间不享受带薪年假，请事假需经总经理特批。"


def generate_contract(index: int, risk: str) -> str:
    company = random.choice(COMPANY_NAMES)
    position = random.choice(POSITIONS)
    location = random.choice(LOCATIONS)

    job_clause = clause_job(risk).replace("{{position}}", position).replace("{{location}}", location)
    noncompete = clause_noncompete(risk)

    return f"""劳动合同

甲方（用人单位）：{company}
乙方（劳动者）：张某

根据《中华人民共和国劳动法》《中华人民共和国劳动合同法》等法律法规，甲乙双方遵循平等自愿、协商一致的原则，订立本合同。

一、劳动合同期限
本合同期限自 2024 年 1 月 1 日起至 2027 年 12 月 31 日止，共三年。

二、工作内容与地点
{job_clause}

三、工作时间
甲方实行标准工时制，每日工作 8 小时，每周工作 5 天。因工作需要安排加班的，依法支付加班费。

四、劳动报酬
{clause_salary(risk)}

五、试用期
{clause_probation(risk)}

六、社会保险
甲方依法为乙方缴纳社会保险（养老、医疗、工伤、失业、生育），个人缴纳部分由乙方承担。

七、离职与解除
{clause_resignation(risk)}

八、休假
{clause_leave(risk)}

九、保密与竞业限制
{noncompete if noncompete else '乙方对在工作期间知悉的甲方商业秘密负有保密义务。'}

十、争议解决
{clause_jurisdiction(risk)}

十一、其他
本合同一式两份，甲乙双方各执一份，自双方签字或盖章之日起生效。

甲方（盖章）：{company}
乙方（签字）：张某
签订日期：2024 年 1 月 1 日
"""


def main() -> None:
    """生成 50 份合同并写入对应目录."""
    distribution = [
        ("low-risk", "low", 15),
        ("medium-risk", "medium", 15),
        ("high-risk", "high", 15),
        ("mixed", random.choice(["low", "medium", "high"]), 5),
    ]

    counter = 0
    for folder, risk, count in distribution:
        out_dir = OUTPUT / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            counter += 1
            contract_risk = risk if folder != "mixed" else random.choice(["low", "medium", "high"])
            text = generate_contract(counter, contract_risk)
            path = out_dir / f"contract_{counter:03d}.txt"
            path.write_text(text, encoding="utf-8")

    print(f"已生成 {counter} 份合同样本，存放于 {OUTPUT}")


if __name__ == "__main__":
    main()
