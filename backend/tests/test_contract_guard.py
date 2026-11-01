"""内容体检单测: 文档类型判定 (L1 规则) + 文件头校验 (L0 magic bytes).

全部为纯函数/纯规则, 不依赖网络、大模型与数据库。
"""

from __future__ import annotations

import asyncio
import io
import zipfile

import pytest

from app.services.contract_guard import (
    CONTRACT_TYPES,
    DocType,
    check_document,
    _classify_by_rules,
)
from app.services.file_signature import sniff_kind, verify_file_content

LABOR_CONTRACT = """劳动合同

甲方：某某科技有限公司
乙方：张三

第一条 合同期限
本合同为固定期限劳动合同，自 2024 年 1 月 1 日起至 2027 年 12 月 31 日止。

第二条 工作内容
乙方同意根据甲方工作需要，担任软件工程师岗位，工作地点为北京。

第三条 劳动报酬
甲方每月以货币形式支付乙方工资人民币 15000 元，试用期工资为 12000 元。

第四条 社会保险
甲方依法为乙方缴纳社会保险，乙方应当配合提供相关材料。

第五条 其他约定
本协议未尽事宜，双方协商解决，任何一方不得擅自解除劳动合同。

甲方（盖章）：            乙方（签字）：
签订日期：2024 年 1 月 1 日
"""

NEWS = """记者昨日从市人社局获悉，今年以来全市共受理劳动争议案件 1.2 万件，同比增长 15%。

发布会上，市人社局副局长表示，劳动仲裁的办理时限将进一步压缩，平均办理周期缩短至 30 天。

“我们希望通过流程优化，让劳动者维权更便捷。”该负责人在接受采访时说。

本报讯 网友在评论区留言称，自己所在公司存在拖欠工资的情况，希望有关部门关注。

责任编辑：李四
"""

RESUME = """个人简历

姓名：王五
教育背景
2015-2019 某某大学 计算机科学与技术 本科

工作经历
2019-2022 某科技公司 后端开发工程师

项目经验
负责订单系统重构，接口平均响应时间下降 60%

专业技能
熟悉 Java、Python、MySQL，了解分布式与消息队列

自我评价
学习能力强，善于沟通，能承担一定的工作压力
"""

INVOICE = """增值税电子普通发票

发票代码：011002000311
发票号码：12345678
开票日期：2024 年 01 月 01 日
购买方名称：某某科技有限公司
销售方名称：某某商贸有限公司
价税合计（大写）：壹仟元整    ￥1000.00
税额：￥130.00
"""


@pytest.mark.parametrize(
    ("text", "expected", "is_contract"),
    [
        (LABOR_CONTRACT, DocType.LABOR_CONTRACT, True),
        (NEWS, DocType.NEWS_ARTICLE, False),
        (RESUME, DocType.RESUME, False),
        (INVOICE, DocType.INVOICE, False),
    ],
)
def test_rule_classification(text: str, expected: DocType, is_contract: bool) -> None:
    result = _classify_by_rules(text)
    assert result.doc_type is expected
    assert result.is_contract is is_contract
    assert 0.0 <= result.confidence <= 1.0
    # 非合同必须给出可展示的提示, 合同高置信时不需要提示
    assert bool(result.notice) is (not is_contract)


def test_labor_contract_is_high_confidence() -> None:
    result = _classify_by_rules(LABOR_CONTRACT)
    assert result.confidence >= 0.6
    assert result.method == "rule"
    assert result.doc_type in CONTRACT_TYPES
    assert result.notice is None


def test_short_text_is_garbage() -> None:
    result = _classify_by_rules("好的，我明天去公司谈一下")
    assert result.doc_type is DocType.GARBAGE
    assert result.is_contract is False
    assert "字" in (result.notice or "")


def test_empty_text_is_garbage() -> None:
    result = _classify_by_rules("   ")
    assert result.doc_type is DocType.GARBAGE
    assert result.is_contract is False
    assert result.confidence >= 0.9


def test_non_chinese_text() -> None:
    text = (
        "This Employment Agreement is made and entered into as of January 1, 2024, "
        "by and between the Company and the Employee, on the terms and conditions "
        "set forth in this Agreement, including but not limited to compensation, "
        "working hours, confidentiality obligations and termination provisions."
    )
    result = _classify_by_rules(text)
    assert result.doc_type is DocType.NON_CHINESE
    assert result.is_contract is False


def test_table_extension_short_circuits() -> None:
    # 表格/演示文稿按文件类型直接判定, 不再看内容
    result = asyncio.run(check_document(LABOR_CONTRACT, ext="xlsx", use_llm=False))
    assert result.doc_type is DocType.SPREADSHEET
    assert result.is_contract is False
    assert result.method == "ext"


def test_check_document_rules_only() -> None:
    result = asyncio.run(check_document(LABOR_CONTRACT, use_llm=False))
    assert result.is_contract is True
    assert result.method == "rule"


def test_to_dict_contract() -> None:
    data = _classify_by_rules(LABOR_CONTRACT).to_dict()
    assert set(data) == {
        "doc_type",
        "doc_type_label",
        "is_contract",
        "confidence",
        "method",
        "reasons",
        "notice",
    }
    assert data["doc_type_label"] == "劳动合同"
    assert data["is_contract"] is True


# ─── L0: 文件头校验 ────────────────────────────────────────────


def _docx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def test_sniff_kind() -> None:
    assert sniff_kind(b"%PDF-1.7\n...") == "pdf"
    assert sniff_kind(_docx_bytes()) == "docx"
    assert sniff_kind(b"\x89PNG\r\n\x1a\n....") == "png"
    assert sniff_kind("甲方：某某公司".encode()) == "text"


def test_pdf_content_passes_pdf_ext() -> None:
    assert verify_file_content("pdf", b"%PDF-1.7\n" + b"x" * 100) is None


def test_pdf_renamed_to_docx_is_rejected() -> None:
    reason = verify_file_content("docx", b"%PDF-1.7\n" + b"x" * 100)
    assert reason is not None
    assert ".docx" in reason
    assert "PDF" in reason


def test_plain_zip_renamed_to_docx_is_rejected() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("a.txt", "hello")
    reason = verify_file_content("docx", buf.getvalue())
    assert reason is not None
    assert "压缩包" in reason


def test_docx_passes_docx_ext() -> None:
    assert verify_file_content("docx", _docx_bytes()) is None


def test_image_renamed_to_txt_is_rejected() -> None:
    reason = verify_file_content("txt", b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    assert reason is not None


def test_plain_text_passes_text_ext() -> None:
    assert verify_file_content("md", "# 劳动合同\n甲方：某某公司".encode()) is None


def test_empty_file_is_rejected() -> None:
    assert verify_file_content("pdf", b"") == "文件内容为空, 请重新选择文件"
