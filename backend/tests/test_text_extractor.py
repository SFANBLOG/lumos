"""
文本抽取服务测试 — 聚焦扫描版 PDF 自动 OCR 分支.

以假 pypdf / fitz 模块与打桩 extract_image 注入, 不依赖真实 PDF 渲染或 OCR 引擎,
验证:
- 有文字层的 PDF 直接返回文字, 不触发 OCR;
- 无文字层 (扫描件) 自动逐页渲染位图并走 OCR 链路;
- OCR 组件 (pymupdf) 缺失时抛 ServiceNotReadyError (由路由转 503)。
"""

from __future__ import annotations

import sys
import types

import pytest

from app.services import text_extractor as te


def _fake_pypdf(page_texts: list[str]) -> types.ModuleType:
    """构造假 pypdf: PdfReader(data).pages 逐页返回给定文字层."""
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


def _fake_fitz(page_count: int, png: bytes = b"PNGDUMMY") -> types.ModuleType:
    """构造假 fitz (PyMuPDF): open 返回可索引文档, 每页渲染为固定 PNG 字节."""
    mod = types.ModuleType("fitz")

    class _Pixmap:
        def tobytes(self, _fmt: str) -> bytes:
            return png

    class _Page:
        def get_pixmap(self, matrix: object = None) -> _Pixmap:  # noqa: ARG002
            return _Pixmap()

    class _Doc:
        def __init__(self, *_a: object, **_k: object) -> None:
            self._pages = [_Page() for _ in range(page_count)]
            self.page_count = page_count
            self.closed = False

        def __getitem__(self, idx: int) -> _Page:
            return self._pages[idx]

        def close(self) -> None:
            self.closed = True

    mod.open = lambda **_kw: _Doc()  # type: ignore[attr-defined]
    mod.Matrix = lambda *a: a  # type: ignore[attr-defined]
    return mod


class TestExtractPdfAutoOcr:
    def test_text_layer_pdf_does_not_trigger_ocr(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["甲方：星辰科技\n竞业限制条款"]))

        def _boom(_data: bytes) -> tuple[str, bool]:
            raise AssertionError("有文字层时不应调用 OCR")

        monkeypatch.setattr(te, "extract_image", _boom)

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is False
        assert "竞业限制" in text

    def test_scanned_pdf_auto_ocr_per_page(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["", ""]))
        monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(page_count=2))

        seen: list[bytes] = []

        def _fake_ocr(data: bytes) -> tuple[str, bool]:
            seen.append(data)
            return (f"第{len(seen)}页识别文本", True)

        monkeypatch.setattr(te, "extract_image", _fake_ocr)

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is True
        assert seen == [b"PNGDUMMY", b"PNGDUMMY"]  # 两页各 OCR 一次
        assert text == "第1页识别文本\n\n第2页识别文本"

    def test_mixed_pdf_only_blank_pages_are_ocred(self, monkeypatch) -> None:
        """混排 PDF: 仅对无文字层的页 OCR, 有文字层的页保留原文; is_scanned=False."""
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf(["第一条正文", "", "第三条正文"]))

        # 让不同页渲染出可区分的位图字节, 以断言只有第 2 页被 OCR
        fitz_mod = _fake_fitz(page_count=3)
        rendered: list[int] = []

        class _Pixmap:
            def __init__(self, idx: int) -> None:
                self._idx = idx

            def tobytes(self, _fmt: str) -> bytes:
                return f"PNG{self._idx}".encode()

        class _Page:
            def __init__(self, idx: int) -> None:
                self._idx = idx

            def get_pixmap(self, matrix: object = None) -> _Pixmap:  # noqa: ARG002
                rendered.append(self._idx)
                return _Pixmap(self._idx)

        class _Doc:
            def __init__(self, *_a: object, **_k: object) -> None:
                self._pages = [_Page(i) for i in range(3)]
                self.page_count = 3

            def __getitem__(self, idx: int) -> _Page:
                return self._pages[idx]

            def close(self) -> None:
                pass

        fitz_mod.open = lambda **_kw: _Doc()  # type: ignore[attr-defined]
        fitz_mod.Matrix = lambda *a: a  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "fitz", fitz_mod)

        def _fake_ocr(data: bytes) -> tuple[str, bool]:
            return ("第二条OCR文本", True)

        monkeypatch.setattr(te, "extract_image", _fake_ocr)

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is False
        assert rendered == [1]  # 仅空白页 (索引 1) 被渲染 OCR
        assert text == "第一条正文\n\n第二条OCR文本\n\n第三条正文"

    def test_scanned_pdf_blank_ocr_keeps_empty(self, monkeypatch) -> None:
        """OCR 返回空白 (引擎读不出) 时仍标记为扫描件且文本为空."""
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf([""]))
        monkeypatch.setitem(sys.modules, "fitz", _fake_fitz(page_count=1))
        monkeypatch.setattr(te, "extract_image", lambda _d: ("   \n ", True))

        text, scanned = te.extract_pdf(b"%PDF-1.4 fake")
        assert scanned is True
        assert text == ""

    def test_missing_pymupdf_raises_service_not_ready(self, monkeypatch) -> None:
        monkeypatch.setitem(sys.modules, "pypdf", _fake_pypdf([""]))
        # fitz 不可用: import fitz 抛 ImportError
        monkeypatch.setitem(sys.modules, "fitz", None)

        with pytest.raises(te.ServiceNotReadyError, match="pymupdf"):
            te.extract_pdf(b"%PDF-1.4 fake")
