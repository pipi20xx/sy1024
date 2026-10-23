
import secrets
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.openapi.docs import get_swagger_ui_html
from typing import List, Optional
from sqlalchemy import desc, select, func
from .. import globals
from ..models import AuditLog
from app.logger import logger, log_audit
from ..database import AuditLogSessionLocal

router = APIRouter(prefix="/api/external-control", tags=["外部控制管理"])

@router.get("/config", summary="获取外部控制配置")
async def get_external_config():
    """获取 API Token 认证和审计日志的相关配置。"""
    config = globals.service.config.get("external_control", {})
    return config

@router.post("/config", summary="更新外部控制配置")
async def update_external_config(request: Request):
    """保存 API Token 认证和审计日志的相关配置。"""
    try:
        new_config = await request.json()
        current_config = globals.service.config.get("external_control", {})
        current_config.update(new_config)
        
        success, message = globals.service.configuration_service.update_config({
            "external_control": current_config
        })
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        return {"message": "配置更新成功", "config": current_config}
    except Exception as e:
        log_audit("外部控制", "失败", f"更新外部控制配置时出错: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate-token", summary="生成 API Token")
async def generate_token():
    """生成一个新的随机 API 访问令牌。"""
    token = secrets.token_hex(32)
    return {"token": token}

@router.get("/audit-logs", summary="获取审计日志")
async def get_audit_logs(page: int = 1, size: int = 50, search: Optional[str] = None):
    """获取 API 访问的审计记录，支持分页和关键词搜索。"""
    async with AuditLogSessionLocal() as db:
        try:
            # 构建查询
            query = select(AuditLog)
            if search:
                query = query.filter(
                    (AuditLog.path.contains(search)) | 
                    (AuditLog.ip.contains(search)) | 
                    (AuditLog.method.contains(search))
                )
            
            # 获取总数
            count_query = select(func.count()).select_from(query.subquery())
            total_res = await db.execute(count_query)
            total = total_res.scalar() or 0
            
            # 分页和排序
            query = query.order_by(desc(AuditLog.timestamp)).offset((page - 1) * size).limit(size)
            result = await db.execute(query)
            logs = result.scalars().all()
            
            return {
                "total": total,
                "items": [log.to_dict() for log in logs],
                "page": page,
                "size": size
            }
        except Exception as e:
            log_audit("外部控制", "失败", f"获取审计日志时出错: {e}", level="ERROR")
            raise HTTPException(status_code=500, detail="获取审计日志失败")

@router.get("/docs-ui", summary="获取 API 文档界面", response_class=HTMLResponse)
async def get_protected_docs(request: Request, theme: str = "dark", auth_token: Optional[str] = None):
    """受保护的 Swagger UI 访问界面，支持自定义主题和自动鉴权。"""
    referer = request.headers.get("referer")
    host = request.headers.get("host")
    
    if not referer or host not in referer:
        pass 

    # 根据主题定义配色
    if theme == "light":
        # 浅色主题
        primary_color = "#705df2"
        bg_color = "#ffffff"
        card_bg = "#f5f5f7"
        text_color = "#1a1a1a"
        border_color = "rgba(0, 0, 0, 0.1)"
        hover_bg = "rgba(0, 0, 0, 0.02)"
        secondary_text = "rgba(0, 0, 0, 0.6)"
        scrollbar_bg = "rgba(0, 0, 0, 0.1)"
    elif theme == "purple":
        # 紫色深色主题
        primary_color = "#bb86fc"
        bg_color = "#0b040f"
        card_bg = "#180a20"
        text_color = "#e0e0e0"
        border_color = "rgba(255, 255, 255, 0.1)"
        hover_bg = "rgba(255, 255, 255, 0.05)"
        secondary_text = "rgba(255, 255, 255, 0.6)"
        scrollbar_bg = "rgba(255, 255, 255, 0.1)"
    else:
        # 默认深色主题
        primary_color = "#705df2"
        bg_color = "#101014"
        card_bg = "#1e1e24"
        text_color = "#e0e0e0"
        border_color = "rgba(255, 255, 255, 0.1)"
        hover_bg = "rgba(255, 255, 255, 0.05)"
        secondary_text = "rgba(255, 255, 255, 0.6)"
        scrollbar_bg = "rgba(255, 255, 255, 0.1)"

    custom_css = f"""
    /* 基础背景与文字 */
    body {{ background-color: {bg_color} !important; margin: 0; padding: 0; }}
    .swagger-ui {{ background-color: {bg_color} !important; color: {text_color} !important; }}
    
    /* 滚动条美化 */
    ::-webkit-scrollbar {{ width: 8px; height: 8px; }}
    ::-webkit-scrollbar-track {{ background: {bg_color}; }}
    ::-webkit-scrollbar-thumb {{ background: {scrollbar_bg}; border-radius: 10px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {primary_color}; }}
    
    /* Firefox 滚动条支持 */
    * {{ scrollbar-width: thin; scrollbar-color: {scrollbar_bg} {bg_color}; }}

    .swagger-ui .topbar {{ display: none; }}
    .swagger-ui .info .title, .swagger-ui .info li, .swagger-ui .info p, .swagger-ui .info table, .swagger-ui .info h1, .swagger-ui .info h2, .swagger-ui .info h3 {{ color: {text_color} !important; }}
    
    /* 接口区块与标签 */
    .swagger-ui .opblock-tag {{ color: {text_color} !important; border-bottom: 1px solid {border_color} !important; }}
    .swagger-ui .opblock-tag:hover {{ background: {hover_bg} !important; }}
    .swagger-ui .opblock {{ background: {card_bg} !important; border: 1px solid {border_color} !important; box-shadow: none !important; }}
    .swagger-ui .opblock .opblock-summary-path {{ color: {text_color} !important; }}
    .swagger-ui .opblock .opblock-summary-description {{ color: {secondary_text} !important; }}
    
    /* 参数与请求配置区 */
    .swagger-ui .scheme-container {{ background: {card_bg} !important; box-shadow: none !important; border-top: 1px solid {border_color} !important; }}
    .swagger-ui select {{ background: {bg_color} !important; color: {text_color} !important; border-color: {border_color} !important; }}
    .swagger-ui input {{ background: {card_bg} !important; color: {text_color} !important; border: 1px solid {border_color} !important; }}
    .swagger-ui .btn {{ color: {text_color} !important; border-color: {border_color} !important; background: transparent !important; }}
    .swagger-ui .btn.execute {{ background-color: {primary_color} !important; border-color: {primary_color} !important; color: #000 !important; font-weight: bold !important; }}
    
    /* 重点：模型 (Models / Schemas) 区块 */
    .swagger-ui .models {{ background: {card_bg} !important; border: 1px solid {border_color} !important; margin: 20px !important; border-radius: 8px !important; }}
    .swagger-ui .models .model-container {{ background: transparent !important; margin: 0 !important; padding: 10px !important; }}
    .swagger-ui .models h4 {{ color: {text_color} !important; border-bottom: 1px solid {border_color} !important; padding-bottom: 10px !important; }}
    .swagger-ui .model-box {{ background: transparent !important; color: {text_color} !important; }}
    .swagger-ui .model-box-control {{ background: transparent !important; color: {text_color} !important; border: none !important; }}
    .swagger-ui .model-box-control:focus {{ outline: none !important; }}
    .swagger-ui .model-wrapper {{ background: transparent !important; }}
    .swagger-ui .model {{ color: {text_color} !important; background: transparent !important; }}
    .swagger-ui .model-title {{ color: {text_color} !important; }}
    .swagger-ui .prop-type {{ color: #f2a3ff !important; }}
    .swagger-ui .prop-format {{ color: {secondary_text} !important; }}
    .swagger-ui .prop-name {{ color: {text_color} !important; font-weight: bold !important; }}
    
    /* 修复 Schemas 内部嵌套表格和列表的白底 */
    .swagger-ui section.models .model-container {{ background-color: transparent !important; }}
    .swagger-ui section.models .model-box {{ background-color: {hover_bg} !important; }}
    .swagger-ui .model-toggle:after {{ filter: invert(1) brightness(2); }}
    
    /* 响应与表格 */
    .swagger-ui table thead tr td, .swagger-ui table thead tr th {{ color: {text_color} !important; border-bottom: 1px solid {border_color} !important; }}
    .swagger-ui .response-col_status {{ color: {text_color} !important; }}
    .swagger-ui section.models h4 {{ color: {text_color} !important; border-bottom: 1px solid {border_color} !important; }}
    .swagger-ui .model-toggle:after {{ filter: invert(1) brightness(2); }}
    .swagger-ui .parameter__name, .swagger-ui .parameter__type, .swagger-ui .parameter__deprecated, .swagger-ui .parameter__in {{ color: {text_color} !important; font-family: monospace !important; }}
    .swagger-ui .parameter__extension, .swagger-ui .parameter__in {{ font-style: italic !important; color: {secondary_text} !important; }}
    
    /* Parameters 专属修复 */
    .swagger-ui .opblock-section-header {{ background: {hover_bg} !important; border-top: 1px solid {border_color} !important; border-bottom: 1px solid {border_color} !important; }}
    .swagger-ui .opblock-section-header h4 {{ color: {text_color} !important; }}
    .swagger-ui .parameters-container, .swagger-ui .responses-container {{ background: transparent !important; }}
    .swagger-ui table.parameters, .swagger-ui table.responses-table {{ background: transparent !important; }}
    .swagger-ui .parameter__name {{ color: {primary_color} !important; font-weight: bold !important; }}
    .swagger-ui .parameter__type {{ color: #f2a3ff !important; }}
    
    /* Markdown 描述 */
    .swagger-ui .renderedMarkdown p, .swagger-ui .renderedMarkdown li {{ color: {secondary_text} !important; }}
    
    /* 修复白底嵌套 */
    .swagger-ui .opblock-body pre {{ background: #111 !important; color: #70ff70 !important; border: 1px solid {border_color} !important; }}

    /* 接口行右侧图标 (锁与箭头) 适配 */
    .swagger-ui .authorization__btn svg {{ fill: {primary_color} !important; }}
    .swagger-ui .opblock-summary-control svg {{ fill: {text_color} !important; opacity: 0.7; }}
    .swagger-ui .opblock-summary-control:hover svg {{ opacity: 1; }}
    .swagger-ui .view-line-link.copy-to-clipboard svg {{ fill: {text_color} !important; }}

    /* 强制调整弹窗位置：使其紧贴顶部工具栏 */
    .swagger-ui .scheme-container {{ position: relative !important; }}
    .swagger-ui .dialog-ux {{ 
        position: absolute !important; 
        top: 100% !important; /* 紧跟在工具栏下方 */
        left: 50% !important; 
        transform: translateX(-50%) !important; 
        z-index: 9999 !important;
        width: 600px !important; /* 加宽一点点 */
    }}
    .swagger-ui .modal-ux-mask {{ 
        position: absolute !important; 
        top: 0 !important; 
        left: 0 !important; 
        width: 100% !important; 
        height: 10000px !important; /* 确保遮罩层足够长以处理点击关闭 */
        z-index: 9998 !important; 
        background: rgba(0, 0, 0, 0.1) !important; /* 极淡的遮罩，方便看清位置 */
    }}
    .swagger-ui .modal-ux {{ 
        background-color: {card_bg} !important; 
        border: 1px solid rgba(255,255,255,0.2) !important;
        border-radius: 8px !important;
        max-height: 700px !important; /* 调高限制，确保 BearerAuth 能看全 */
        overflow-y: auto !important; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.5) !important;
    }}
    .swagger-ui .modal-ux-content {{ padding: 20px !important; }}
    .swagger-ui .auth-container {{ padding: 15px 0 !important; }}
    .swagger-ui .modal-ux-content {{ 
        padding: 15px !important; 
    }}
    .swagger-ui .modal-ux-header {{ 
        border-bottom: 1px solid rgba(255,255,255,0.1) !important; 
        padding: 10px 15px !important;
    }}
    .swagger-ui .modal-ux-header h3 {{ color: {text_color} !important; }}
    .swagger-ui .modal-ux-content {{ background-color: {bg_color} !important; }}
    .swagger-ui .modal-ux-content h4 {{ color: {text_color} !important; }}
    .swagger-ui .auth-container {{ color: {text_color} !important; border-bottom: 1px solid rgba(255,255,255,0.1) !important; }}
    .swagger-ui .auth-container:last-of-type {{ border-bottom: none !important; }}
    .swagger-ui .auth-container label {{ color: {text_color} !important; }}
    .swagger-ui .auth-btn-wrapper {{ justify-content: center !important; gap: 10px !important; }}
    .swagger-ui .modal-ux-content p {{ color: rgba(255,255,255,0.6) !important; }}

    /* 适配新版 JSON Schema 2020-12 渲染器 */
    .json-schema-2020-12-accordion {{ background: transparent !important; border: none !important; color: {text_color} !important; }}
    .json-schema-2020-12-accordion__children {{ color: {text_color} !important; }}
    .json-schema-2020-12__title {{ color: {text_color} !important; font-weight: bold !important; }}
    .json-schema-2020-12-accordion__icon svg {{ fill: {text_color} !important; }}
    .json-schema-2020-12-accordion:hover {{ background: rgba(255,255,255,0.05) !important; }}
    .json-schema-2020-12-expand-deep-button {{ 
        color: {primary_color} !important; 
        background: transparent !important; 
        border: 1px solid {primary_color} !important; 
        border-radius: 4px !important;
        padding: 2px 8px !important;
        cursor: pointer !important;
        font-size: 12px !important;
    }}
    .json-schema-2020-12-expand-deep-button:hover {{ 
        background: {primary_color} !important; 
        color: #000 !important; 
    }}
    """

    if auth_token:
        # 使用自定义初始化方式，注入 requestInterceptor 使所有请求自动带 Authorization header
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TMDB Metadata Browser API - Documentation</title>
    <link rel="stylesheet" type="text/css" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <style>{custom_css}</style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
    window.onload = function() {{
        window.ui = SwaggerUIBundle({{
            url: "/api/openapi.json",
            dom_id: '#swagger-ui',
            deepLinking: true,
            presets: [
                SwaggerUIBundle.presets.apis
            ],
            layout: "BaseLayout",
            requestInterceptor: function(req) {{
                req.headers['Authorization'] = 'Bearer {auth_token}';
                return req;
            }}
        }});
        setTimeout(function() {{
            if (window.ui) {{
                window.ui.authActions.authorize({{
                    "BearerAuth": {{
                        name: "BearerAuth",
                        schema: {{
                            type: "http",
                            scheme: "bearer",
                            bearerFormat: "JWT"
                        }},
                        value: "{auth_token}"
                    }}
                }});
            }}
        }}, 1500);
    }};
    </script>
</body>
</html>"""
        return HTMLResponse(content=html_content)

    resp = get_swagger_ui_html(
        openapi_url="/api/openapi.json",
        title="TMDB Metadata Browser API - Documentation",
        swagger_js_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css",
    )
    
    # 将 CSS 注入到生成的 HTML 中
    html_content = resp.body.decode("utf-8")
    custom_injection = f"<style>{custom_css}</style>"
    html_content = html_content.replace("</head>", f"{custom_injection}</head>")
    
    return HTMLResponse(content=html_content)

