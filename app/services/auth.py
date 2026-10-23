import asyncio
import base64
import io
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
import re

import pyotp
import qrcode
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.session import Session
from app.schemas.auth import LoginRequest, TokenResponse, TwoFactorSetupResponse, UserInfoResponse
from app.utils.auth import create_access_token, get_password_hash, verify_password, verify_token_version
from app.utils.rate_limit import login_limiter
from app.models import AuditLog
from app.database import AuditLogSessionLocal, SessionsSessionLocal
from app.services.configuration import ConfigurationService
from app.utils.time import get_local_time
from app.logger import log_audit

class AuthService:
    
    @staticmethod
    def _parse_user_agent(user_agent: str) -> dict:
        """解析User-Agent获取设备信息"""
        device_info = {
            "device_name": "未知设备",
            "device_type": "Unknown"
        }
        
        if not user_agent:
            return device_info
        
        ua = user_agent.lower()
        
        if "windows" in ua:
            device_info["device_type"] = "Windows"
        elif "mac" in ua or "os x" in ua:
            device_info["device_type"] = "macOS"
        elif "linux" in ua:
            device_info["device_type"] = "Linux"
        elif "android" in ua:
            device_info["device_type"] = "Android"
        elif "iphone" in ua or "ipad" in ua:
            device_info["device_type"] = "iOS"
        elif "mobile" in ua:
            device_info["device_type"] = "Mobile"
        
        if "chrome" in ua:
            device_info["device_name"] = "Chrome"
        elif "firefox" in ua:
            device_info["device_name"] = "Firefox"
        elif "safari" in ua:
            device_info["device_name"] = "Safari"
        elif "edge" in ua:
            device_info["device_name"] = "Edge"
        elif "opera" in ua:
            device_info["device_name"] = "Opera"
        
        return device_info
    
    @staticmethod
    async def _add_audit_log(method: str, path: str, status_code: int, ip: str, payload: str):
        """内部辅助方法：记录审计日志到数据库"""
        try:
            async with AuditLogSessionLocal() as db_session:
                log_entry = AuditLog(
                    timestamp=datetime.now().isoformat(),
                    method=method,
                    path=path,
                    status_code=status_code,
                    ip=ip,
                    query_params="",
                    payload=payload,
                    user_agent="AuthService"
                )
                db_session.add(log_entry)
                await db_session.commit()
        except Exception as e:
            logging.getLogger(__name__).error("写入审计日志失败: %s", e)

    @staticmethod
    async def authenticate_user(db: AsyncSession, req: LoginRequest, request: Request, client_ip: str) -> TokenResponse:
        # 1. Rate Limit Check
        is_locked, remaining = login_limiter.is_locked(client_ip)
        if is_locked:
            log_audit("认证", "登录拒绝", f"IP: {client_ip}, 封锁中 (剩余 {remaining}s)", level="WARN")
            raise HTTPException(status_code=429, detail=f"封锁中，请在 {remaining} 秒后再试")

        # 2. User Lookup
        result = await db.execute(select(User).where(User.username == req.username))
        user = result.scalars().first()

        # 3. Password Verification
        if not user or not verify_password(req.password, user.hashed_password):
            login_limiter.record_failure(client_ip)
            log_audit("认证", "登录失败", f"用户: {req.username}, IP: {client_ip}", level="ERROR")
            asyncio.create_task(
                AuthService._add_audit_log("POST", "/api/auth/login", 401, client_ip, payload=f"登录失败: {req.username}")
            )
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 4. 2FA Verification
        if user.is_otp_enabled:
            if not req.otp_code:
                # Return pending token for 2FA flow
                pending_token = create_access_token(
                    data={"sub": user.username, "type": "2fa_pending"}, expires_delta=timedelta(minutes=5)
                )
                return TokenResponse(
                    access_token=pending_token, token_type="bearer", username=user.username, status="2fa_required"
                )

            totp = pyotp.TOTP(user.otp_secret)
            if not totp.verify(req.otp_code):
                login_limiter.record_failure(client_ip)
                log_audit("认证", "2FA失败", f"用户: {user.username}, IP: {client_ip}", level="ERROR")
                raise HTTPException(status_code=401, detail="2FA 验证码错误")

        # 5. Success Handling
        login_limiter.reset(client_ip)
        user.last_login = get_local_time()
        await db.commit()

        # 获取配置，判断是否开启永久登录
        config_service = ConfigurationService()
        config = config_service.get_config()
        permanent_login = config.get("permanent_login_enabled", False)

        # 生成会话ID
        session_id = secrets.token_urlsafe(32)
        
        # 解析设备信息
        user_agent = request.headers.get("user-agent", "")
        device_info = AuthService._parse_user_agent(user_agent)
        
        # 计算会话过期时间
        if permanent_login:
            session_expires_at = get_local_time() + timedelta(days=365 * 10)  # 10年
        else:
            session_expires_at = get_local_time() + timedelta(hours=24)  # 24小时，与JWT一致
        
        # 创建会话记录
        async with SessionsSessionLocal() as session_db:
            new_session = Session(
                session_id=session_id,
                user_id=user.id,
                device_name=device_info["device_name"],
                device_type=device_info["device_type"],
                ip_address=client_ip,
                user_agent=user_agent,
                login_time=get_local_time(),
                last_activity=get_local_time(),
                expires_at=session_expires_at
            )
            session_db.add(new_session)
            await session_db.commit()

        access_token = create_access_token(
            data={
                "sub": user.username, 
                "token_version": user.token_version,
                "session_id": session_id
            },
            permanent=permanent_login
        )

        log_audit("认证", "登录成功", f"用户: {user.username}, IP: {client_ip}, 设备: {device_info['device_name']}", level="SUCCESS")
        asyncio.create_task(
            AuthService._add_audit_log("POST", "/api/auth/login", 200, client_ip, payload=f"登录成功: {user.username}")
        )

        return TokenResponse(access_token=access_token, token_type="bearer", username=user.username, status="success")

    @staticmethod
    async def change_password(db: AsyncSession, username: str, old_pass: str, new_pass: str):
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        if not verify_password(old_pass, user.hashed_password):
            log_audit("认证", "修改密码失败", f"用户: {username}, 旧密码错误", level="WARN")
            raise HTTPException(status_code=400, detail="旧密码错误")

        user.hashed_password = get_password_hash(new_pass)
        user.token_version += 1
        await db.commit()
        log_audit("认证", "修改密码", f"用户: {username}", level="SUCCESS")
        asyncio.create_task(
            AuthService._add_audit_log("POST", "/api/auth/password", 200, "internal", payload=f"用户 {username} 修改密码")
        )

    @staticmethod
    async def setup_2fa_secret(db: AsyncSession, username: str) -> TwoFactorSetupResponse:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        secret = pyotp.random_base32()
        user.otp_secret = secret
        await db.commit()

        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="TMDB-Editor")
        img = qrcode.make(totp_uri)
        
        # Convert QR code to base64
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()

        return TwoFactorSetupResponse(secret=secret, qr_code=f"data:image/png;base64,{img_str}")

    @staticmethod
    async def enable_2fa(db: AsyncSession, username: str, code: str):
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        if not user.otp_secret:
            raise HTTPException(status_code=400, detail="请先请求 2FA 设置")

        totp = pyotp.TOTP(user.otp_secret)
        if not totp.verify(code):
            raise HTTPException(status_code=400, detail="验证码错误")

        user.is_otp_enabled = True
        await db.commit()
        log_audit("认证", "启用2FA", f"用户: {username}", level="SUCCESS")
        return {"message": "2FA 已成功开启"}

    @staticmethod
    async def disable_2fa(db: AsyncSession, username: str):
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")

        user.is_otp_enabled = False
        user.otp_secret = None
        await db.commit()
        log_audit("认证", "关闭2FA", f"用户: {username}", level="WARN")
        return {"message": "2FA 已关闭"}

    @staticmethod
    async def get_current_user_info(db: AsyncSession, username: str) -> UserInfoResponse:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        if not user:
            raise HTTPException(status_code=401, detail="用户不存在")
            
        return UserInfoResponse(
            username=user.username,
            is_otp_enabled=user.is_otp_enabled,
            last_login=user.last_login.isoformat() if user.last_login else None
        )
