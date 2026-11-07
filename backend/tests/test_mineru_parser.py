"""
MinerU 版面解析适配层测试 — 不依赖真实 MinerU / 模型权重 / 网络.

以打桩的 subprocess.run、假 httpx 模块、假 pypdf 模块注入, 覆盖:
- CLI 4.x / 2.x 两种命令形态与产物收集 (Markdown + content_list + 图片);
- CLI 失败/超时的显式不可用语义;
- content_list 结构化块归一化 (表格 HTML → 纯文本 / 图片 / 公式);
- 版面图片块交给多模态视觉模型补识并回填;
- HTTP 内网解析服务响应解析;
- extract_pdf_detailed 的 auto 回退 / mineru fail-loud / 正常解析三条分支。
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from app.services import mineru_parser as mp
from app.services import text_extractor as te

_MARKDOWN = """# 劳动合同

甲方：星辰科技

| 项目 | 约定 |
| --- | --- |
| 竞业限制 | 2 年 |

![](images/seal.png)
"""

_CONTENT_LIST = [
    {"type": "title", "text": "劳动合同", "page_idx": 0},
    {"type": "text", "text": "甲方：星辰科技", "page_idx": 0},
    {
        "type": "table",
        "table_caption": "约定表",
        "table_body": (
            "<table><tr><td>项目</td><td>约定</td></tr>"
            "<tr><td>竞业限制</td><td>2 年</td></tr></table>"
        ),
        "page_idx": 0,
    },
    {"type": "image", "image_caption": "公章", "img_path": "images/seal.png", "page_idx": 0},
]


def _settings(**overrides: object) -> types.SimpleNamespace:
    """构造与 Settings 字段同名的轻量配置对象 (便于单测覆盖)."""
    base: dict[str, object] = dict(
        pdf_parser_strategy="auto",
        mineru_backend="cli",
        mineru_cli="",
        mineru_cli_flavor="v4",
        mineru_tier="standard",
        mineru_method="auto",
        mineru_http_url="",
        mineru_http_token="",
        mineru_timeout_seconds=5,
        mineru_vision_enrich=False,
        mineru_vision_max_images=6,
        image_ocr_strategy="auto",
        # 内置 legacy 链路 (lumos 副本) 会读取的三个开关
        pdf_cross_page_table_merge=False,
        pdf_layout_geometry=False,
        pdf_column_aware_extract=False,
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _fake_pypdf(page_texts: list[str]) -> types.ModuleType:
    mod = types.ModuleType("pypdf")

    class _Page:
        def __init__(self, text: str) -> None:
            self._text = text

        def extract_text(self) -> str:
            return self._text

    class _Reader:
        def __init__(self, _data: object) -> None:
            self.pages = [_Page(t) for t in page_texts]

    mod.PdfReader = _Reader  # type: ignore[attr-defined]
    return mod


def _fake_cli(tmp_path: Path, name: str) -> str:
    """造一个真实存在的假可执行文件, 绕过 shutil.which 探测."""
    path = tmp_path / name
    path.write_text("", encoding="utf-8")
    return str(path)


def _completed(cmd: list[str], code: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(cmd, code, stdout="", stderr=stderr)


# ─── CLI 后端 ──────────────────────────────────────────────────


def test_cli_v4_collects_markdown_content_list_and_images(monkeypatch, tmp_path) -> None:
    cli = _fake_cli(tmp_path, "mineru-kit")
    seen: dict[str, list[str]] = {}

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("-o") + 1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(_MARKDOWN, encoding="utf-8")
        (out.parent / "sample_content_list.json").write_text(
            json.dumps(_CONTENT_LIST, ensure_ascii=False), encoding="utf-8"
        )
        (out.parent / "images").mkdir(exist_ok=True)
        (out.parent / "images" / "seal.png").write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return _completed(cmd)

    monkeypatch.setattr(mp.subprocess, "run", _run)
    result = mp.parse_pdf(b"%PDF-1.4 fake", _settings(mineru_cli=cli))

    assert result.engine == "mineru:cli:v4"
    assert "竞业限制" in result.text
    assert "--tier" in seen["cmd"] and "standard" in seen["cmd"]
    assert [b.type for b in result.blocks] == ["title", "text", "table", "image"]
    assert "项目 | 约定" in result.blocks[2].text
    assert result.page_count == 1
    assert len(result.images) == 1 and result.images[0][0] == "images/seal.png"


def test_cli_v2_uses_legacy_command_shape(monkeypatch, tmp_path) -> None:
    cli = _fake_cli(tmp_path, "mineru")
    seen: dict[str, list[str]] = {}

    def _run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        seen["cmd"] = cmd
        out = Path(cmd[cmd.index("-o") + 1])
        (out / "auto").mkdir(parents=True, exist_ok=True)
        (out / "auto" / "contract.md").write_text("# 合同\n第二条 试用期", encoding="utf-8")
        return _completed(cmd)

    monkeypatch.setattr(mp.subprocess, "run", _run)
    result = mp.parse_pdf(
        b"%PDF-1.4 fake",
        _settings(mineru_cli=cli, mineru_cli_flavor="v2", mineru_method="ocr"),
    )

    assert "-p" in seen["cmd"] and "-m" in seen["cmd"] and "ocr" in seen["cmd"]
    assert result.engine == "mineru:cli:v2"
    assert "试用期" in result.text


def test_cli_nonzero_exit_is_explicitly_unavailable(monkeypatch, tmp_path) -> None:
    cli = _fake_cli(tmp_path, "mineru-kit")
    monkeypatch.setattr(
        mp.subprocess,
        "run",
        lambda cmd, **_kw: _completed(cmd, code=1, stderr="model missing"),
    )
    with pytest.raises(mp.MinerUUnavailable, match="退出码"):
        mp.parse_pdf(b"%PDF-1.4 fake", _settings(mineru_cli=cli))


def test_cli_timeout_is_explicitly_unavailable(monkeypatch, tmp_path) -> None:
    cli = _fake_cli(tmp_path, "mineru-kit")

    def _timeout(cmd: list[str], **_kw: object) -> None:
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(mp.subprocess, "run", _timeout)
    with pytest.raises(mp.MinerUUnavailable, match="超时"):
        mp.parse_pdf(b"%PDF-1.4 fake", _settings(mineru_cli=cli))


def test_no_cli_and_no_http_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(mp.shutil, "which", lambda _cmd: None)
    with pytest.raises(mp.MinerUUnavailable, match="未找到 MinerU CLI"):
        mp.parse_pdf(
            b"%PDF-1.4 fake",
            _settings(mineru_backend="auto", mineru_cli="", mineru_http_url=""),
        )


# ─── content_list 归一化 ───────────────────────────────────────


def test_content_list_normalizes_table_image_and_equation() -> None:
    blocks = mp._parse_content_list(
        {
            "content_list": [
                {
                    "type": "table",
                    "table_body": "<table><tr><td>甲</td><td>乙</td></tr></table>",
                    "page_idx": "1",
                },
                {
                    "type": "image",
                    "img_path": "images/a.png",
                    "image_caption": ["公章", "扫描件"],
                },
                {"type": "equation", "latex": "a^2+b^2=c^2", "page_idx": 2},
            ]
        }
    )
    assert [b.type for b in blocks] == ["table", "image", "equation"]
    assert "甲 | 乙" in blocks[0].text
    assert blocks[0].page_idx == 1
    assert blocks[1].image_path == "images/a.png"
    assert "公章" in blocks[1].text
    assert "a^2+b^2=c^2" in blocks[2].text


# ─── 多模态视觉补识 ────────────────────────────────────────────


def test_enrich_with_vision_replaces_image_reference() -> None:
    result = mp.MinerUResult(
        text="前文\n\n![](images/seal.png)\n\n后文",
        engine="test",
        images=[("images/seal.png", b"\x89PNG\r\n\x1a\nFAKE")],
    )
    count = mp.enrich_with_vision(
        result,
        _settings(mineru_vision_enrich=True),
        vision_fn=lambda _d: ("公章：星辰科技", True),
    )
    assert count == 1
    assert result.vision_enriched == 1
    assert "【图片内容·多模态识别】" in result.text
    assert "公章：星辰科技" in result.text
    assert "![" not in result.text


def test_enrich_vision_failure_keeps_layout_text() -> None:
    result = mp.MinerUResult(
        text="正文\n\n![](images/seal.png)",
        engine="test",
        images=[("images/seal.png", b"PNG")],
    )

    def _boom(_data: bytes) -> str:
        raise RuntimeError("vision down")

    count = mp.enrich_with_vision(
        result, _settings(mineru_vision_enrich=True), vision_fn=_boom
    )
    assert count == 0
    assert "正文" in result.text
    assert "![" not in result.text  # 失效的临时路径引用被清掉
    assert result.warnings


# ─── HTTP 后端 ─────────────────────────────────────────────────


def _fake_httpx(monkeypatch, payload: dict) -> dict:
    fake = types.ModuleType("httpx")
    calls: dict = {}

    class _Response:
        headers = {"content-type": "application/json"}
        text = json.dumps(payload, ensure_ascii=False)

        def json(self) -> dict:
            return payload

        def raise_for_status(self) -> None:
            return None

    def _post(url: str, **kwargs: object) -> _Response:
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _Response()

    fake.post = _post  # type: ignore[attr-defined]
    fake.HTTPError = type("HTTPError", (Exception,), {})  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "httpx", fake)
    return calls


def test_http_backend_parses_markdown_content_list_and_base64_images(monkeypatch) -> None:
    payload = {
        "markdown": "# 劳动合同\n\n![](images/seal.png)",
        "content_list": _CONTENT_LIST,
        "images": {"images/seal.png": base64.b64encode(b"PNG").decode("ascii")},
    }
    calls = _fake_httpx(monkeypatch, payload)
    result = mp.parse_pdf(
        b"%PDF-1.4 fake",
        _settings(
            mineru_backend="http",
            mineru_http_url="http://127.0.0.1:8100/v1/file_parse",
            mineru_http_token="secret",
        ),
    )
    assert result.engine == "mineru:http"
    assert "劳动合同" in result.text
    assert any(b.type == "table" for b in result.blocks)
    assert result.images and result.images[0][1] == b"PNG"
    assert calls["kwargs"]["headers"]["Authorization"] == "Bearer secret"


def test_http_backend_without_url_is_unavailable() -> None:
    with pytest.raises(mp.MinerUUnavailable, match="MINERU_HTTP_URL"):
        mp.parse_pdf(b"%PDF-1.4 fake", _settings(mineru_backend="http", mineru_http_url=""))


# ─── 与 text_extractor 主链的集成 ──────────────────────────────


def test_auto_strategy_falls_back_and_reports_reason(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["甲方：星辰科技"]))
    monkeypatch.setattr(mp.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: _settings(
            pdf_parser_strategy="auto",
            mineru_backend="auto",
            mineru_cli="",
            mineru_http_url="",
        ),
    )

    text, scanned, meta = te.extract_pdf_detailed(b"%PDF-1.4 fake")
    assert "星辰科技" in text
    assert scanned is False
    assert meta.parser == "legacy"
    assert "MinerU" in meta.fallback_reason
    assert meta.to_dict()["parser"] == "legacy"


def test_mineru_strategy_is_fail_loud_when_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(mp.shutil, "which", lambda _cmd: None)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: _settings(
            pdf_parser_strategy="mineru",
            mineru_backend="auto",
            mineru_cli="",
            mineru_http_url="",
        ),
    )
    with pytest.raises(te.ServiceNotReadyError, match="MinerU"):
        te.extract_pdf_detailed(b"%PDF-1.4 fake")


def test_mineru_strategy_uses_layout_parser_when_available(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["甲方正文"]))
    parsed = mp.MinerUResult(
        text="# 劳动合同\n竞业限制 2 年",
        engine="mineru:cli:v4",
        blocks=[mp.MinerUBlock("text", "竞业限制 2 年", 0)],
    )
    monkeypatch.setattr(mp, "parse_pdf", lambda _data, _s: parsed)
    monkeypatch.setattr(mp, "enrich_with_vision", lambda _r, _s: 0)
    monkeypatch.setattr(
        "app.core.config.get_settings",
        lambda: _settings(pdf_parser_strategy="mineru"),
    )

    text, scanned, meta = te.extract_pdf_detailed(b"%PDF-1.4 fake")
    assert "竞业限制 2 年" in text
    assert scanned is False
    assert meta.parser == "mineru"
    assert meta.detail == "mineru:cli:v4"


def test_extract_by_ext_detailed_non_pdf_returns_default_meta() -> None:
    text, scanned, meta = te.extract_by_ext_detailed("txt", "hello".encode("utf-8"))
    assert text == "hello"
    assert scanned is False
    assert meta.parser == "legacy"
    assert meta.fallback_reason == ""
