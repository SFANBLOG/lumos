"""
生成 100 份「全部不重复、覆盖合同全部情况」的中文劳动合同样本。

用于测试 Lumos 合同风险分析系统的覆盖能力。

目录结构（风险区 + 坑点 二级）：
    contracts/
    ├── 高危区/ 竞业禁止 | 试用期社保 | 强制扣薪   (各 10 份)
    ├── 警惕区/ 岗位职责 | 服从一切安排 | 离职审批 (各 10 份)
    ├── 关注区/ 休假权益 | 管辖地争议 | 培训服务期 (各 10 份)
    └── 综合区/                                (10 份，混合多种风险)

覆盖维度（保证「全部情况」）：
    - 12 种合同形式：标准劳动/劳务/实习/兼职/劳务派遣/业务外包/平台用工/
      退休返聘/竞业限制/保密/培训服务期/离职解除
    - 多行业公司、多岗位、多地区、多劳动者姓名
    - 每条合同各条款随机低/中/高风险变体（按风险区加权），且「焦点坑点」用对应风险档
    - 公司/岗位/地区/姓名/金额/期限等字段随机化，确保 100 条文本互不重复

去重：构建时对每条全文做唯一性校验，若撞车则更换劳动者姓名重试。
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

random.seed(20240907)

BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "contracts"

# ---------------------------------------------------------------------------
# 基础词库（扩大以保证差异化与真实感）
# ---------------------------------------------------------------------------
COMPANIES = [
    "星辰科技有限公司", "蓝海创新股份有限公司", "云帆网络科技", "金盾劳务服务有限公司",
    "鼎盛人力资源集团", "华夏咨询管理有限公司", "鹏程物流有限公司", "启航教育科技",
    "瑞丰金融信息服务", "博远文化传媒", "恒泰智能制造有限公司", "康宁生物医药",
    "舌尖美味餐饮管理", "锦绣服饰实业", "广厦建筑工程", "星河房地产开发",
    "智联互联网医院", "顺风速运物流", "万象数据科技", "悦动体育文化",
]
POSITIONS = [
    "高级软件工程师", "产品经理", "市场专员", "人事主管", "财务分析师",
    "UI 设计师", "销售代表", "运营专员", "法务助理", "行政助理",
    "仓库管理员", "网约车司机", "外卖配送员", "收银员", "客服专员",
    "护士", "教师", "厨师", "保安", "保洁员",
]
LOCATIONS = [
    "北京市朝阳区", "上海市浦东新区", "深圳市南山区", "广州市天河区", "杭州市西湖区",
    "成都市高新区", "武汉市东湖高新区", "南京市建邺区", "西安市雁塔区", "苏州市工业园区",
    "重庆市渝中区", "天津市滨海新区", "青岛市崂山区", "厦门市思明区", "长沙市岳麓区",
]
EMPLOYEES = [
    "张某", "李某", "王某", "赵某", "刘某", "陈某", "杨某", "黄某", "周某某", "吴某某",
    "徐某", "孙某某", "马某某", "朱某某", "胡某某", "林某某", "郭某某", "何某", "高某某", "罗某某",
    "梁某", "宋某", "唐某", "韩某", "冯某", "邓某", "曹某", "彭某", "曾某", "肖某",
]

# ---------------------------------------------------------------------------
# 合同形式（覆盖「合同的全部情况」）
# ---------------------------------------------------------------------------
FORMS = [
    ("标准劳动合同", "甲乙双方建立全日制劳动关系，适用《劳动合同法》。"),
    ("劳务协议", "双方为劳务关系，不适用《劳动合同法》关于劳动关系之强制规定。"),
    ("实习协议", "乙方为在校学生，本协议为实习协议，不建立劳动关系。"),
    ("兼职协议", "乙方以非全日制用工形式提供劳动，平均每日工作不超过四小时。"),
    ("劳务派遣协议", "甲方为劳务派遣单位，乙方被派遣至实际用工单位工作。"),
    ("业务外包协议", "甲方将部分业务外包给乙方，乙方自行组织人员完成。"),
    ("平台用工协议", "乙方通过甲方平台自主接单，收入按单结算，工作时间灵活。"),
    ("退休返聘协议", "乙方已依法享受养老保险待遇并退休，双方为劳务关系。"),
    ("竞业限制协议", "本协议专门约定乙方离职后的竞业限制义务与补偿。"),
    ("保密协议", "本协议专门约定乙方对甲方商业秘密的保密义务。"),
    ("培训服务期协议", "甲方出资为乙方提供专项培训，约定服务期与违约责任。"),
    ("离职解除协议", "甲乙双方协商一致解除劳动合同，约定补偿与后续义务。"),
]

# ---------------------------------------------------------------------------
# 坑点 -> (对应条款函数, 焦点风险档)
# ---------------------------------------------------------------------------
PITFALLS = {
    "竞业禁止": ("noncompete", "high"),
    "试用期社保": ("social", "high"),
    "强制扣薪": ("salary", "high"),
    "岗位职责": ("job", "medium"),
    "服从一切安排": ("job", "medium"),
    "离职审批": ("resignation", "medium"),
    "休假权益": ("leave", "medium"),
    "管辖地争议": ("jurisdiction", "medium"),
    "培训服务期": ("training", "medium"),
}

ZONE_PITFALLS = {
    "高危区": ["竞业禁止", "试用期社保", "强制扣薪"],
    "警惕区": ["岗位职责", "服从一切安排", "离职审批"],
    "关注区": ["休假权益", "管辖地争议", "培训服务期"],
}
ZONE_WEIGHTS = {
    "高危区": {"high": 0.6, "medium": 0.3, "low": 0.1},
    "警惕区": {"high": 0.25, "medium": 0.55, "low": 0.20},
    "关注区": {"high": 0.10, "medium": 0.35, "low": 0.55},
}


def pick_severity(zone: str) -> str:
    w = ZONE_WEIGHTS[zone]
    return random.choices(list(w), weights=list(w.values()))[0]


# ---------------------------------------------------------------------------
# 各条款生成器（按风险档返回文本，含随机化细节）
# ---------------------------------------------------------------------------
def clause_probation(sev: str) -> str:
    if sev == "low":
        m = random.randint(1, 3)
        p = random.choice([90, 95, 100])
        return f"试用期为 {m} 个月，试用期工资为转正工资的 {p}%，并依法缴纳社会保险。"
    if sev == "medium":
        m = random.randint(1, 3)
        return f"试用期为 {m} 个月，试用期工资为转正工资的 80%。"
    m = random.randint(3, 6)
    return f"试用期为 {m} 个月，试用期工资为转正工资的 70%，试用期期间不缴纳社会保险。"


def clause_salary(sev: str) -> str:
    if sev == "low":
        day = random.choice([10, 15, 20])
        return f"甲方每月 {day} 日前以货币形式足额支付乙方工资，不得无故克扣或拖欠。"
    if sev == "medium":
        return "甲方每月支付乙方工资；如因乙方工作失误造成公司损失，甲方可从工资中扣除赔偿，但每月扣除部分不超过当月工资的 20%。"
    return "甲方有权根据乙方工作表现、考勤及主观评价任意扣减乙方工资，无需事先通知，并有权延迟发放工资。"


def clause_job(sev: str, position: str, location: str) -> str:
    if sev == "low":
        return f"乙方岗位为 {position}，工作地点为 {location}，具体工作内容以岗位职责说明书为准。"
    return "乙方需服从甲方的一切合理安排，甲方有权根据经营需要随时调整乙方的工作岗位、工作地点及工作内容，乙方不得拒绝。"


def clause_resignation(sev: str) -> str:
    if sev == "low":
        return "乙方提前三十日以书面形式通知甲方，可以解除劳动合同。"
    if sev == "medium":
        return "乙方辞职需经甲方批准，未经批准擅自离职的，需赔偿甲方一个月工资作为代通知金。"
    n = random.choice([8, 10, 15, 20])
    return f"乙方在服务期内不得提出辞职，否则需向甲方支付违约金人民币 {n} 万元。"


def clause_noncompete(sev: str) -> str:
    if sev == "low":
        return "乙方对在工作期间知悉的甲方商业秘密负有保密义务。"
    y = random.choice([1, 2]) if sev == "medium" else random.choice([2, 3])
    c = random.choice([500, 800, 1000])
    if sev == "medium":
        return f"乙方离职后 {y} 年内不得从事与甲方业务相近的工作，甲方每月支付竞业限制补偿金人民币 {c} 元。"
    big = random.choice([30, 50, 80])
    return (f"乙方在职期间及离职后 {y} 年内不得从事与甲方业务相同或相近的工作，否则需支付违约金人民币 {big} 万元；"
            f"甲方每月支付竞业限制补偿金人民币 {c} 元（远低于法定标准）。")


def clause_jurisdiction(sev: str, location: str) -> str:
    if sev == "low":
        return "因履行本合同发生争议，双方可向劳动合同履行地劳动争议仲裁委员会申请仲裁。"
    return f"因履行本合同发生争议，双方同意由甲方所在地（{location}）劳动争议仲裁委员会仲裁。"


def clause_leave(sev: str) -> str:
    if sev == "low":
        return "乙方依法享有法定节假日、年休假、病假、婚假、产假等假期，带薪年休假按法律规定执行。"
    if sev == "medium":
        d = random.choice([3, 5])
        return f"乙方工作满一年后享有 {d} 天带薪年假。"
    return "乙方工作期间不享受带薪年假，请事假需经总经理特批且期间不计薪。"


def clause_training(sev: str) -> str:
    if sev == "low":
        return "甲方为乙方提供岗前培训，不约定服务期。"
    y = random.choice([2, 3]) if sev == "medium" else random.choice([4, 5])
    if sev == "medium":
        return f"甲方出资为乙方提供专项培训，约定服务期 {y} 年；若乙方提前离职，需按比例返还培训费用。"
    n = random.choice([10, 15, 20])
    return f"甲方为乙方提供专项培训，约定服务期 {y} 年，违约金人民币 {n} 万元（含工资收入折算）。"


def clause_social(sev: str) -> str:
    if sev == "low":
        return "甲方依法为乙方缴纳社会保险（养老、医疗、工伤、失业、生育），个人缴纳部分由乙方承担。"
    if sev == "medium":
        return "甲方为乙方缴纳社会保险，但自试用期转正后开始缴纳，试用期间不参保。"
    x = random.choice([300, 500, 800])
    return f"甲方不为乙方缴纳社会保险，相关补贴已计入工资（每月 {x} 元）。"


CLAUSE_FUNCS = {
    "probation": clause_probation,
    "salary": clause_salary,
    "job": clause_job,
    "resignation": clause_resignation,
    "noncompete": clause_noncompete,
    "jurisdiction": clause_jurisdiction,
    "leave": clause_leave,
    "training": clause_training,
    "social": clause_social,
}


def build_contract(form_title: str, form_note: str, company: str, position: str,
                  location: str, employee: str, focus: tuple[str, str] | None) -> str:
    """构造一份完整合同文本。focus=(pitfall_clause_key, severity) 时强制该条款为该风险档。"""
    focus_key, focus_sev = focus if focus else (None, None)

    # 其它条款按风险区随机档
    sev = {k: pick_severity(zone_of(focus_key)) if focus_key else "low"
           for k in CLAUSE_FUNCS}

    # 焦点条款强制为指定风险档
    if focus_key:
        sev[focus_key] = focus_sev

    text = f"""{form_title}

甲方（用人单位）：{company}
乙方（劳动者）：{employee}

根据《中华人民共和国劳动法》《中华人民共和国劳动合同法》等法律法规，甲乙双方遵循平等自愿、协商一致的原则，订立本协议/合同。
（说明：{form_note}）

一、合同期限
本合同期限自 2024 年 1 月 1 日起至 2027 年 12 月 31 日止，共三年。

二、工作内容与地点
{CLAUSE_FUNCS['job'](sev['job'], position, location)}

三、工作时间
甲方实行标准工时制，每日工作 8 小时，每周工作 5 天。因工作需要安排加班的，依法支付加班费。

四、劳动报酬
{CLAUSE_FUNCS['salary'](sev['salary'])}

五、试用期
{CLAUSE_FUNCS['probation'](sev['probation'])}

六、社会保险
{CLAUSE_FUNCS['social'](sev['social'])}

七、离职与解除
{CLAUSE_FUNCS['resignation'](sev['resignation'])}

八、休假
{CLAUSE_FUNCS['leave'](sev['leave'])}

九、保密与竞业限制
{CLAUSE_FUNCS['noncompete'](sev['noncompete'])}

十、争议解决
{CLAUSE_FUNCS['jurisdiction'](sev['jurisdiction'], location)}

十一、培训服务期
{CLAUSE_FUNCS['training'](sev['training'])}

十二、其他
本合同一式两份，甲乙双方各执一份，自双方签字或盖章之日起生效。

甲方（盖章）：{company}
乙方（签字）：{employee}
签订日期：2024 年 1 月 1 日
"""
    return text


def zone_of(clause_key: str | None) -> str:
    if clause_key is None:
        return "关注区"
    for zone, pits in ZONE_PITFALLS.items():
        for p in pits:
            if PITFALLS[p][0] == clause_key:
                return zone
    return "关注区"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True, exist_ok=True)

    seen: set[str] = set()
    counter = 0
    plan: list[tuple[str, str, tuple[str, str] | None]] = []

    # 9 坑点 × 10 份
    for zone, pits in ZONE_PITFALLS.items():
        for pit in pits:
            for _ in range(10):
                plan.append((zone, pit, PITFALLS[pit]))

    # 综合区 10 份（混合多种风险，无单一焦点，但随机带 2~3 个坑点）
    for _ in range(10):
        plan.append(("综合区", "综合", None))

    form_cycle = FORMS * ((len(plan) // len(FORMS)) + 1)

    for idx, (zone, pit, focus) in enumerate(plan):
        form_title, form_note = form_cycle[idx]
        company = random.choice(COMPANIES)
        position = random.choice(POSITIONS)
        location = random.choice(LOCATIONS)
        employee = random.choice(EMPLOYEES)

        # 综合区：随机挑 2~3 个坑点并随机风险档，拼成多风险合同
        if focus is None:
            n_focus = random.randint(2, 3)
            picks = random.sample(list(PITFALLS.items()), n_focus)
            # picks 元素为 (坑点名, (条款键, 风险档))
            (_, (fkey, fsev)), *extra = picks
            text = build_contract(form_title, form_note, company, position, location, employee, (fkey, fsev))
            extra_lines = "\n".join(
                (f"【附加风险条款】{pn}："
                 + (CLAUSE_FUNCS[ck](sv) if ck != 'job'
                    else CLAUSE_FUNCS['job'](sv, position, location)))
                for pn, (ck, sv) in extra
            )
            text = text.replace("十二、其他", f"十二、其他\n{extra_lines}")
        else:
            fkey, fsev = focus
            text = build_contract(form_title, form_note, company, position, location, employee, (fkey, fsev))

        # 去重保障：撞车则更换劳动者姓名重试
        tries = 0
        while text in seen and tries < 20:
            employee = random.choice(EMPLOYEES)
            if focus is None:
                text = build_contract(form_title, form_note, company, position, location, employee, (fkey, fsev))
            else:
                text = build_contract(form_title, form_note, company, position, location, employee, (fkey, fsev))
            tries += 1
        assert text not in seen, "仍出现重复合同，请检查生成逻辑"
        seen.add(text)

        # 落盘
        if pit == "综合":
            out_dir = OUTPUT / "综合区"
        else:
            out_dir = OUTPUT / zone / pit
        out_dir.mkdir(parents=True, exist_ok=True)
        counter += 1
        path = out_dir / f"劳动合同样本_{counter:03d}.txt"
        path.write_text(text, encoding="utf-8")

    print(f"已生成 {counter} 份不重复合同样本，存放于 {OUTPUT}")
    print(f"唯一性校验通过：distinct={len(seen)} / total={counter}")


if __name__ == "__main__":
    main()
