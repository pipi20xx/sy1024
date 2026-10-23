import time
import json
from typing import Optional
from app.logger import log_audit
import asyncio
from datetime import datetime
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request
from starlette.responses import Response
from app import globals
from app.models import AuditLog


# 认证豁免路径 - 只保留真正必要的接口
EXEMPT_PATHS = [
    "/api/system/login",      # 登录接口必须豁免
    "/api/auth/login",        # 登录接口必须豁免
    "/api/emby-collections/images",  # 合集图片资源（img标签加载，无法携带header）
    "/api/webhook/",          # Webhook接口（外部服务调用，使用URL token验证）
    "/tmdb-mock/",            # TMDB Mock API — 透明代理，供 Emby/Jellyfin 等外部客户端使用，等同于 TMDB 官方 API
    "/api/appearance/wallpaper_proxy",  # 壁纸图片（img/CSS/WebGL 纹理加载，无法携带 header）
    "/api/appearance/wallpaper/uploads",  # 已上传壁纸图片（缩略图 img 标签加载，无法携带 header）
]


class ExternalControlMiddleware:
    """纯 ASGI 中间件，替代 BaseHTTPMiddleware 以兼容 StreamingResponse (SSE)。"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        # --- HTTP 请求处理 ---
        request = Request(scope, receive, send)

        config = globals.service.config.get("external_control", {})
        api_token = config.get("api_token")
        audit_log_enabled = config.get("audit_log_enabled", True)

        protected_prefixes = ("/api", "/tmdb-mock", "/ws")
        is_protected_path = any(request.url.path.startswith(p) for p in protected_prefixes)
        is_exempt = any(request.url.path.startswith(p) for p in EXEMPT_PATHS)

        if is_protected_path and not is_exempt:
            valid_token = await self._authenticate(request, api_token)
            if not valid_token:
                response = Response(
                    content=json.dumps({"detail": "Unauthorized"}),
                    status_code=401,
                    media_type="application/json"
                )
                await response(scope, receive, send)
                return

        # 读取请求体用于审计日志（仅对写操作）
        payload = ""
        body_read = False
        request_body = b""
        if audit_log_enabled and is_protected_path and not is_exempt:
            if request.method in ("POST", "PUT", "PATCH"):
                request_body = await request.body()
                body_read = True
                try:
                    body_json = json.loads(request_body)
                    self._mask_sensitive_data(body_json)
                    payload = json.dumps(body_json, ensure_ascii=False)
                except Exception:
                    payload = request_body.decode(errors='ignore')[:1000]

        # 只有读取了 body 时才需要回放，否则直接使用原始 receive
        if body_read:
            body_consumed = [False]

            async def receive_with_body():
                if not body_consumed[0]:
                    body_consumed[0] = True
                    return {"type": "http.request", "body": request_body}
                return await receive()

            downstream_receive = receive_with_body
        else:
            downstream_receive = receive

        start_time = time.time()

        # 记录响应状态码
        response_status_code = [0]

        async def send_with_status(message):
            if message["type"] == "http.response.start":
                response_status_code[0] = message.get("status", 0)
            await send(message)

        await self.app(scope, downstream_receive, send_with_status)

        process_time = time.time() - start_time

        if audit_log_enabled and is_protected_path:
            # 构造一个伪 response 对象仅用于记录状态码
            class _FakeResponse:
                def __init__(self, status_code):
                    self.status_code = status_code
            fake_response = _FakeResponse(response_status_code[0])
            asyncio.create_task(self._save_audit_log(request, fake_response, payload))

    async def _authenticate(self, request: Request, api_token: Optional[str] = None) -> bool:
        """验证请求的认证信息，返回是否有效。"""
        auth_header = request.headers.get("Authorization")
        url_token = request.query_params.get("auth_token")

        if auth_header and auth_header.startswith("Bearer "):
            provided_token = auth_header[7:]
            if api_token and provided_token == api_token:
                return True
            elif provided_token:
                return await self._verify_jwt_token(provided_token, request)
        elif url_token:
            return await self._verify_jwt_token(url_token, request)

        return False

    async def _verify_jwt_token(self, token: str, request: Request) -> bool:
        """验证 JWT token 并检查会话有效性。"""
        from app.utils.auth import decode_access_token, verify_token_version
        from app.database import UsersSessionLocal, SessionsSessionLocal
        from app.models.user import User
        from app.models.session import Session
        from sqlalchemy import select

        payload = decode_access_token(token)
        if not payload:
            log_audit("认证", "校验", f"Token解析失败: {request.method} {request.url.path}", level="WARN")
            return False

        username = payload.get("sub")
        session_id = payload.get("session_id")
        token_version = payload.get("token_version")

        if not username:
            return False

        async with UsersSessionLocal() as db:
            result = await db.execute(select(User).where(User.username == username))
            user = result.scalars().first()
            if not user:
                log_audit("认证", "校验", f"用户不存在: username={username}", level="WARN")
                return False

            if token_version is not None:
                if not verify_token_version(payload, user.token_version):
                    log_audit("认证", "校验", f"Token版本不匹配: token={token_version}, user={user.token_version}", level="WARN")
                    return False
                elif session_id:
                    async with SessionsSessionLocal() as session_db:
                        session_result = await session_db.execute(
                            select(Session)
                            .where(Session.session_id == session_id)
                            .where(Session.user_id == user.id)
                        )
                        session = session_result.scalars().first()
                        if not session:
                            log_audit("认证", "校验", f"会话不存在: session_id={session_id}", level="WARN")
                            return False
                        elif not session.is_active:
                            log_audit("认证", "校验", f"会话已失效: session_id={session_id}", level="WARN")
                            return False
                        else:
                            return True
                else:
                    return True
            else:
                log_audit("认证", "校验", f"Token缺少token_version字段: username={username}", level="WARN")
                return False

    def _mask_sensitive_data(self, data):
        """递归屏蔽敏感关键字"""
        sensitive_keys = {"password", "token", "api_key", "secret"}
        if isinstance(data, dict):
            for k, v in data.items():
                if any(sk in k.lower() for sk in sensitive_keys):
                    data[k] = "******"
                else:
                    self._mask_sensitive_data(v)
        elif isinstance(data, list):
            for item in data:
                self._mask_sensitive_data(item)

    async def _save_audit_log(self, request: Request, response, payload: str):
        try:
            # 排除掉获取日志和 Swagger 的 API，防止无限递归和资源消耗
            if "/api/external-control" in request.url.path or "/openapi.json" in request.url.path:
                return

            from app.database import AuditLogSessionLocal

            async with AuditLogSessionLocal() as db_session:
                log_entry = AuditLog(
                    timestamp=datetime.now().isoformat(),
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    ip=request.client.host if request.client else "unknown",
                    query_params=str(request.query_params),
                    payload=payload,
                    user_agent=request.headers.get("user-agent", "")
                )
                db_session.add(log_entry)
                await db_session.commit()
        except Exception as e:
            # 使用 logger 而不是 print，并确保不影响主流程
            log_audit("审计", "保存", f"保存审计日志失败: {e}", level="ERROR")
