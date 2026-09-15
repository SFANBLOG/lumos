"""
认证路由.

提供用户注册、登录、获取个人信息接口。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.future import select

from app.api.deps import DBSession, get_current_user
from app.core.security import create_access_token, create_captcha_challenge, hash_password, verify_captcha_challenge, verify_password
from app.models.user import User, UserRole
from app.services.audit import record_audit_event
from app.core.config import get_settings

router = APIRouter(prefix="/auth", tags=["🔐 认证"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    captcha_token: str = Field(min_length=1)
    captcha_answer: str = Field(min_length=1, max_length=8)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class PasswordResetRequest(BaseModel):
    """本地部署的账户核验式密码重置请求。"""

    username: str = Field(min_length=3, max_length=64)
    email: EmailStr
    new_password: str = Field(min_length=8, max_length=128)
    captcha_token: str = Field(min_length=1)
    captcha_answer: str = Field(min_length=1, max_length=8)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CaptchaResponse(BaseModel):
    question: str
    token: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    is_active: bool
    role: UserRole

    class Config:
        from_attributes = True


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
async def register(
    request: RegisterRequest,
    session: DBSession,
) -> User:
    """注册新用户."""
    if not verify_captcha_challenge(request.captcha_token, request.captcha_answer):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期，请刷新后重试")
    # 检查用户名/邮箱是否已存在
    result = await session.execute(
        select(User).where(
            (User.username == request.username) | (User.email == request.email)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名或邮箱已存在",
        )

    user = User(
        username=request.username,
        email=request.email,
        hashed_password=hash_password(request.password),
        role=(UserRole.OWNER if request.email.lower() in get_settings().bootstrap_owner_email_set else UserRole.MEMBER),
    )
    session.add(user)
    await record_audit_event(
        session,
        action="user.registered",
        resource_type="user",
        resource_id=user.id,
        actor_id=user.id,
        details={"username": user.username},
    )
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/captcha", response_model=CaptchaResponse, summary="获取注册验证码")
async def get_captcha() -> CaptchaResponse:
    """返回一次短时有效的注册验证码挑战。"""
    question, token = create_captcha_challenge()
    return CaptchaResponse(question=question, token=token)


@router.post("/password-reset", summary="重置密码")
async def reset_password(request: PasswordResetRequest, session: DBSession) -> dict[str, str]:
    """通过用户名、注册邮箱和短时验证码重置密码，不暴露账户是否存在。"""
    if not verify_captcha_challenge(request.captcha_token, request.captcha_answer):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="验证码错误或已过期，请刷新后重试")
    result = await session.execute(
        select(User).where(User.username == request.username, User.email == request.email)
    )
    user = result.scalar_one_or_none()
    if user and user.is_active:
        user.hashed_password = hash_password(request.new_password)
        session.add(user)
        await record_audit_event(
            session, action="user.password_reset", resource_type="user", resource_id=user.id,
            actor_id=user.id, details={"username": user.username},
        )
        await session.commit()
    return {"message": "如账户信息匹配，密码已重置，请使用新密码登录"}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="用户登录",
)
async def login(
    request: LoginRequest,
    session: DBSession,
) -> TokenResponse:
    """用户登录并返回 JWT."""
    result = await session.execute(
        select(User).where(User.username == request.username)
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已停用",
        )

    access_token = create_access_token(data={"sub": user.id})
    return TokenResponse(access_token=access_token)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="获取当前登录用户信息",
)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """获取当前登录用户信息."""
    return current_user
