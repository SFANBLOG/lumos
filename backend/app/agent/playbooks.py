"""企业审查 Playbook：后续可由工作区配置替换。"""
from __future__ import annotations

DEFAULT_PLAYBOOK = {
    "name": "劳动者权益基线",
    "position": "employee_friendly",
    "rules": [
        "试用期工资不得低于法定标准，社保不得以试用期为由缺失。",
        "竞业限制须明确范围、期限、补偿；不得泛化限制就业。",
        "不得以笼统服从安排、任意调岗或不合理扣薪规避法定权益。",
        "必须核查工时、休假、离职、违约金、培训服务期与争议管辖。",
    ],
}

def render_playbook() -> str:
    return "\n".join([f"## 企业审查 Playbook：{DEFAULT_PLAYBOOK['name']}", *[f"- {rule}" for rule in DEFAULT_PLAYBOOK["rules"]]])
