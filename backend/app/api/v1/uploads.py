"""
文件上传路由.

支持 PDF/Word 合同上传到 MinIO 对象存储。
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import AuthGuard, DBSession
from app.core.minio_client import upload_file

router = APIRouter(prefix="/uploads", tags=["📤 文件上传"])

_ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
}


@router.post(
    "",
    summary="上传合同文件",
    description="上传 PDF/Word 合同文件到 MinIO，返回文件访问标识。",
)
async def upload_contract_file(
    session: DBSession,
    _auth: AuthGuard,
    file: UploadFile = File(...),  # noqa: B008
    contract_id: str | None = Form(None),
) -> dict:
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PDF/Word 文件",
        )

    data = await file.read()
    suffix = _ALLOWED_TYPES[file.content_type]
    object_name = f"contracts/{contract_id or 'temp'}_{file.filename}"

    upload_file(
        object_name=object_name,
        data=data,
        length=len(data),
        content_type=file.content_type,
    )

    return {
        "object_name": object_name,
        "filename": file.filename,
        "content_type": file.content_type,
        "size": len(data),
    }
