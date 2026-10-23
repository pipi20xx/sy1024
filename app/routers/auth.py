from fastapi import APIRouter, Depends, HTTPException, Request, Body
from typing import Optional
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from app.database import get_users_db, get_sessions_db, users_engine
from app.models.user import User, Base
from app.models.session import Session as SessionModel
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    TokenResponse,
    TwoFactorSetupResponse,
    UserInfoResponse,
)
from app.services.auth import AuthService
from app.utils.auth import decode_access_token, get_password_hash, verify_token_version
from app import globals
from app.utils.time import get_local_time
from app.logger import log_audit

router = APIRouter(prefix="/api/auth", tags=["用户认证"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# --- 依赖项 ---
async def get_current_username(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_users_db)) -> str:
    """获取当前用户名"""
    if not token:
        raise HTTPException(status_code=401, detail="未提供认证凭证")
        
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="无效的凭证")
    
    username = payload.get("sub")
    
    # 验证 token_version
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    if not verify_token_version(payload, user.token_version):
        raise HTTPException(status_code=401, detail="凭证已失效，请重新登录")
    
    return username

async def get_current_username_strict(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_users_db)) -> str:
    """严格模式：需要完成二次验证"""
    if not token:
        raise HTTPException(status_code=401, detail="未提供认证凭证")

    payload = decode_access_token(token)
    if not payload or payload.get("type") == "2fa_pending":
        raise HTTPException(status_code=401, detail="需要完成二次验证")
    
    username = payload.get("sub")
    
    # 验证 token_version
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    if not verify_token_version(payload, user.token_version):
        raise HTTPException(status_code=401, detail="凭证已失效，请重新登录")
    
    return username

# --- 初始化 ---
@router.on_event("startup")
async def init_auth_db():
    """初始化用户数据库并创建默认管理员"""
    async with users_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 检查是否存在管理员，不存在则创建
    async with users_engine.connect() as conn:
        async with conn.begin(): 
             pass

    # 使用 Session 进行数据初始化更稳妥
    from app.database import UsersSessionLocal
    async with UsersSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == "admin"))
        user = result.scalars().first()
        if not user:
            new_user = User(
                username="admin", 
                hashed_password=get_password_hash("admin123"),
                is_active=True
            )
            db.add(new_user)
            await db.commit()
            log_audit("认证", "初始化", "已创建默认管理员账户", level="INFO")

# --- 路由 ---

@router.post("/login", response_model=TokenResponse, summary="管理员登录")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_users_db)):
    client_ip = request.client.host if request.client else "unknown"
    return await AuthService.authenticate_user(db, req, request, client_ip)

@router.post("/password", summary="修改管理员密码")
async def change_password(
    req: PasswordChangeRequest, db: AsyncSession = Depends(get_users_db), username: str = Depends(get_current_username)
):
    await AuthService.change_password(db, username, req.old_password, req.new_password)
    return {"message": "成功"}

@router.get("/2fa/setup", response_model=TwoFactorSetupResponse, summary="获取 2FA 设置信息")
async def setup_2fa(db: AsyncSession = Depends(get_users_db), username: str = Depends(get_current_username)):
    return await AuthService.setup_2fa_secret(db, username)

@router.post("/2fa/enable", summary="正式开启 2FA")
async def enable_2fa(code: str, db: AsyncSession = Depends(get_users_db), username: str = Depends(get_current_username)):
    return await AuthService.enable_2fa(db, username, code)

@router.post("/2fa/disable", summary="关闭 2FA")
async def disable_2fa(db: AsyncSession = Depends(get_users_db), username: str = Depends(get_current_username)):
    return await AuthService.disable_2fa(db, username)

@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
async def get_me(db: AsyncSession = Depends(get_users_db), username: str = Depends(get_current_username_strict)):
    return await AuthService.get_current_user_info(db, username)

@router.get("/sessions", summary="获取所有会话")
async def get_sessions(
    request: Request,
    db: AsyncSession = Depends(get_users_db), 
    session_db: AsyncSession = Depends(get_sessions_db),
    username: str = Depends(get_current_username_strict)
):
    """获取当前用户的所有活跃会话"""
    from sqlalchemy import desc
    from datetime import timedelta
    
    # 获取用户ID
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 获取所有会话
    sessions_result = await session_db.execute(
        select(SessionModel)
        .where(SessionModel.user_id == user.id)
        .where(SessionModel.is_active == True)
        .order_by(desc(SessionModel.login_time))
    )
    sessions = sessions_result.scalars().all()
    
    # 获取当前会话ID
    from app.utils.auth import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    current_session_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload:
            current_session_id = payload.get("session_id")
    
    # 格式化返回
    return [
        {
            "id": s.id,
            "session_id": s.session_id,
            "device_name": s.device_name,
            "device_type": s.device_type,
            "ip_address": s.ip_address,
            "user_agent": s.user_agent,
            "login_time": s.login_time.isoformat() if s.login_time else None,
            "last_activity": s.last_activity.isoformat() if s.last_activity else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            "is_current": s.session_id == current_session_id,
            "expires_in_hours": int((s.expires_at - get_local_time()).total_seconds() / 3600) if s.expires_at else 0
        }
        for s in sessions
    ]

@router.delete("/sessions/{session_id}", summary="踢出指定会话")
async def revoke_session(
    session_id: str,
    db: AsyncSession = Depends(get_users_db),
    session_db: AsyncSession = Depends(get_sessions_db),
    username: str = Depends(get_current_username_strict)
):
    """踢出指定会话"""
    # 获取用户ID
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 查找会话
    session_result = await session_db.execute(
        select(SessionModel)
        .where(SessionModel.session_id == session_id)
        .where(SessionModel.user_id == user.id)
    )
    session = session_result.scalars().first()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 标记为不活跃
    session.is_active = False
    await session_db.commit()
    log_audit("认证", "踢出会话", f"用户: {username}, 会话: {session_id[:8]}...", level="WARN")
    
    return {"message": "会话已踢出"}

@router.delete("/sessions", summary="踢出所有其他会话")
async def revoke_all_other_sessions(
    request: Request,
    db: AsyncSession = Depends(get_users_db),
    session_db: AsyncSession = Depends(get_sessions_db),
    username: str = Depends(get_current_username_strict)
):
    """踢出除当前会话外的所有会话"""
    # 获取用户ID
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 获取当前会话ID
    from app.utils.auth import decode_access_token
    auth_header = request.headers.get("Authorization", "")
    current_session_id = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload:
            current_session_id = payload.get("session_id")
    
    # 踢出所有其他会话
    sessions_result = await session_db.execute(
        select(SessionModel)
        .where(SessionModel.user_id == user.id)
        .where(SessionModel.session_id != current_session_id)
        .where(SessionModel.is_active == True)
    )
    sessions = sessions_result.scalars().all()
    
    for session in sessions:
        session.is_active = False
    
    await session_db.commit()
    log_audit("认证", "踢出全部会话", f"用户: {username}, 踢出 {len(sessions)} 个会话", level="WARN")
    
    return {"message": f"已踢出 {len(sessions)} 个会话"}

@router.post("/sessions/update-expiry", summary="更新所有会话的过期时间")
async def update_sessions_expiry(
    request: Request,
    db: AsyncSession = Depends(get_users_db),
    session_db: AsyncSession = Depends(get_sessions_db),
    username: str = Depends(get_current_username_strict)
):
    """根据当前设置更新所有会话的过期时间"""
    from app.services.configuration import ConfigurationService
    from app.utils.time import get_local_time
    from datetime import timedelta
    
    # 获取用户ID
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    # 获取当前设置
    config_service = ConfigurationService()
    config = config_service.get_config()
    permanent_login = config.get("permanent_login_enabled", False)
    
    # 计算新的过期时间
    if permanent_login:
        new_expiry = get_local_time() + timedelta(days=365 * 10)  # 10年
    else:
        new_expiry = get_local_time() + timedelta(hours=24)  # 24小时
    
    # 更新所有活跃会话
    sessions_result = await session_db.execute(
        select(SessionModel)
        .where(SessionModel.user_id == user.id)
        .where(SessionModel.is_active == True)
    )
    sessions = sessions_result.scalars().all()
    
    updated_count = 0
    for session in sessions:
        session.expires_at = new_expiry
        updated_count += 1
    
    await session_db.commit()
    
    return {"message": f"已更新 {updated_count} 个会话的过期时间"}
