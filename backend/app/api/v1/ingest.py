"""
智能导入路由.

- POST /ingest/file: 上传 pdf/txt/docx/csv, 原文存 MinIO, 返回抽取文本
- POST /ingest/url:  抓取网页链接, 抽取正文, 返回文本

抽取结果不直接入库, 由前端确认后走 POST /contracts 提交分析。
"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.api.deps import AuthAny
from app.core.minio_client import StorageUnavailableError, upload_file
from app.services.contract_guard import check_document
from app.services.file_signature import verify_file_content
from app.services.text_extractor import (
    ServiceNotReadyError,
    extract_by_ext,
    html_to_text,
    truncate,
)

router = APIRouter(prefix="/ingest", tags=["📥 智能导入"])

_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
_MAX_URL_SIZE = 2 * 1024 * 1024  # 2 MB 网页正文
_USER_AGENT = "Mozilla/5.0 (compatible; LumosBot/0.2; +https://lumos.local)"

_ALLOWED_EXT = {
    "pdf", "txt", "docx", "csv", "md", "html", "htm", "rtf", "xlsx", "pptx",
    "png", "jpg", "jpeg", "gif", "webp", "bmp",
}
_ALLOWED_MIME = {
    "pdf": "application/pdf",
    "txt": "text/plain",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "csv": "text/csv",
    "md": "text/markdown",
    "html": "text/html",
    "htm": "text/html",
    "rtf": "application/rtf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
}


class UrlIngestRequest(BaseModel):
    """网页链接导入请求."""

    url: str = Field(..., min_length=8, max_length=2048, description="目标网页链接")


class TextIngestRequest(BaseModel):
    """纯文本导入请求 (粘贴入口预览判定用)."""

    text: str = Field(..., min_length=1, max_length=100_000, description="粘贴的合同/条款文本")


@router.post(
    "/file",
    summary="上传文件并抽取文本",
    description="支持 文档(pdf/docx/txt/csv/md/html/rtf/xlsx/pptx) 与 图片(png/jpg/jpeg/gif/webp/bmp, 走 OCR 抽取文字) (≤10MB)，原文件存档 MinIO，返回抽取出的纯文本。",
)
async def ingest_file(
    _auth: AuthAny,
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    filename = file.filename or "upload"
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"仅支持 {', '.join(sorted(_ALLOWED_EXT))} 文件",
        )

    data = await file.read()
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="文件超过 10MB 上限",
        )

    # L0: 文件头与后缀一致性校验 —— 改名换后缀的文件不进解析器
    mismatch = verify_file_content(ext, data)
    if mismatch:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=mismatch,
        )

    # 原文存档 MinIO, 便于后续追溯
    object_name = f"ingest/{uuid.uuid4()}.{ext}"
    try:
        upload_file(
            object_name=object_name,
            data=data,
            length=len(data),
            content_type=file.content_type or _ALLOWED_MIME.get(ext, "application/octet-stream"),
        )
    except StorageUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    try:
        text, scanned = extract_by_ext(ext, data)
    except ServiceNotReadyError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e

    text, truncated = truncate(text)
    # L1+L2: 判定抽出的正文是不是合同, 结果随响应下发供前端即时提示
    doc_check = await check_document(text, ext=ext)
    return {
        "filename": filename,
        "ext": ext,
        "size": len(data),
        "char_count": len(text),
        "text": text,
        "truncated": truncated,
        "scanned": scanned,
        "object_name": object_name,
        "doc_check": doc_check.to_dict(),
    }


@router.post(
    "/url",
    summary="抓取网页链接并抽取正文",
    description="仅接受 http/https 且返回 text/html 的页面 (≤2MB)。",
)
async def ingest_url(
    req: UrlIngestRequest,
    _auth: AuthAny,
) -> dict:
    parsed = urlparse(req.url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="仅支持 http/https 网页链接",
        )

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=12.0,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            resp = await client.get(req.url)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"抓取失败: {type(e).__name__}",
        ) from e

    content_type = resp.headers.get("content-type", "").lower()
    if "text/html" not in content_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"目标页面非 HTML 内容 (content-type: {content_type or '未知'})",
        )
    if len(resp.content) > _MAX_URL_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="页面超过 2MB, 请尝试精简后的原文链接",
        )

    title, text = html_to_text(resp.text)
    text, truncated = truncate(text)
    # L1+L2: 网页正文同样要判定是不是合同 (新闻/商品页/博客会被识别出来)
    doc_check = await check_document(text)
    return {
        "url": str(resp.url),
        "title": title,
        "char_count": len(text),
        "text": text,
        "truncated": truncated,
        "doc_check": doc_check.to_dict(),
    }


@router.post(
    "/text",
    summary="纯文本预览判定 (不落库)",
    description="粘贴入口在提交前做一次轻量判定, 返回 doc_check 供前端即时提示; 不写 MinIO、不落库。",
)
async def ingest_text(
    _auth: AuthAny,
    req: TextIngestRequest,
) -> dict:
    text, truncated = truncate(req.text)
    # 仅规则判定即可满足预览需求, 避免每次输入停顿都触发大模型调用
    doc_check = await check_document(text, use_llm=False)
    return {
        "char_count": len(text),
        "text": text,
        "truncated": truncated,
        "doc_check": doc_check.to_dict(),
    }
