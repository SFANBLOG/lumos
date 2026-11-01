"""上传文件的真实类型校验 (L0: magic bytes).

扩展名可以被随意修改: 把 .exe / .zip 改名成 .pdf 就能绕过白名单, 直接送进
解析器甚至大模型。这里只做「廉价、确定性」的一致性校验 —— 用文件头判断
实际容器类型, 与后缀比对; 至于内容"是不是合同", 交给 contract_guard。

设计原则: 宁可放过可疑文本, 也不误杀真实文件。判断不确定时返回 None。
"""

from __future__ import annotations

import io
import zipfile

#: OOXML (docx/xlsx/pptx) 都是 zip 容器, 靠内部目录名区分
_OOXML_PREFIX: tuple[tuple[str, str], ...] = (
    ("word/", "docx"),
    ("xl/", "xlsx"),
    ("ppt/", "pptx"),
)

#: 图片文件头 -> 归一化后缀
_IMAGE_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
    (b"BM", "bmp"),
)

#: 纯文本类后缀: 只要求"是文本", 不要求特定内容
_TEXT_EXTS = {"txt", "md", "csv", "html", "htm", "rtf"}

#: 图片类后缀 -> 期望的嗅探结果
_IMAGE_EXTS = {
    "png": "png",
    "jpg": "jpg",
    "jpeg": "jpg",
    "gif": "gif",
    "webp": "webp",
    "bmp": "bmp",
}

_SNIFF_LABELS = {
    "pdf": "PDF 文档",
    "docx": "Word 文档",
    "xlsx": "Excel 表格",
    "pptx": "PPT 演示文稿",
    "zip": "压缩包",
    "png": "PNG 图片",
    "jpg": "JPEG 图片",
    "gif": "GIF 图片",
    "webp": "WebP 图片",
    "bmp": "BMP 图片",
    "rtf": "RTF 文档",
    "binary": "二进制文件",
    "text": "纯文本",
}


def sniff_kind(data: bytes) -> str:
    """按文件头推断真实类型; 无法判断时返回 ``binary`` 或 ``text``."""
    if not data:
        return "binary"
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except Exception:  # noqa: BLE001 - 损坏的 zip 按压缩包处理
            return "zip"
        for prefix, kind in _OOXML_PREFIX:
            if any(name.startswith(prefix) for name in names):
                return kind
        return "zip"
    for magic, kind in _IMAGE_MAGIC:
        if data.startswith(magic):
            return kind
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"{\\rtf"):
        return "rtf"
    if b"\x00" in data[:4096]:
        return "binary"
    return "text"


def verify_file_content(ext: str, data: bytes) -> str | None:
    """校验文件内容与后缀是否一致.

    Returns:
        ``None`` 表示通过; 否则返回可直接展示给用户的中文原因.
    """
    if not data:
        return "文件内容为空, 请重新选择文件"

    kind = sniff_kind(data)
    label = _SNIFF_LABELS.get(kind, kind)

    if ext == "pdf":
        ok = kind == "pdf"
    elif ext in {"docx", "xlsx", "pptx"}:
        ok = kind == ext
    elif ext in _IMAGE_EXTS:
        ok = kind == _IMAGE_EXTS[ext]
    elif ext in _TEXT_EXTS:
        # 文本类: 允许 text / rtf, 明确是二进制/文档容器则拒绝
        ok = kind in {"text", "rtf"} if ext == "rtf" else kind == "text"
    else:
        return None  # 未知后缀交给上层白名单处理

    if ok:
        return None
    return f"文件内容与 .{ext} 后缀不符（实际是{label}），请上传真实的 {ext.upper()} 文件"
