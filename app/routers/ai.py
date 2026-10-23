from fastapi import APIRouter, HTTPException, Body, Depends
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import re
from .. import globals
from ..services.llm_service import LLMService
from app.logger import logger, log_audit

router = APIRouter(prefix="/api/ai", tags=["AI 实验室"])

# --- 请求模型 ---
class TranslationRequest(BaseModel):
    text: str
    context: str = "movie_overview"
    extra_info: Optional[Dict[str, Any]] = None

class BatchTranslationRequest(BaseModel):
    texts: List[str]
    context: str = "actor_name"
    extra_info: Optional[Dict[str, Any]] = None

# 依赖注入获取 LLMService
def get_llm_service():
    if not hasattr(globals, "llm_service") or globals.llm_service is None:
        globals.llm_service = LLMService(globals.service.configuration_service)
    return globals.llm_service

@router.get("/config", summary="获取 AI 配置")
async def get_ai_config():
    return globals.service.config.get("ai", {})

@router.get("/presets", summary="获取 AI 提示词预设")
async def get_ai_presets():
    import os
    import json
    from fastapi.responses import JSONResponse
    # 使用更稳妥的路径定位
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    preset_path = os.path.join(base_dir, "definitions", "ai_presets.json")
    
    log_audit("AI", "处理", f"🔍 尝试读取 AI 预设文件: {preset_path}")
    if os.path.exists(preset_path):
        try:
            with open(preset_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                log_audit("AI", "完成", f"✅ 成功读取 AI 预设，包含 {len(data)} 个模板")
                return JSONResponse(content=data)
        except Exception as e:
            log_audit("AI", "失败", f"读取 AI 预设文件失败: {e}", level="ERROR")
    else:
        log_audit("AI", "处理", f"AI 预设文件不存在: {preset_path}", level="WARN")
    return JSONResponse(content={})

@router.post("/config", summary="更新 AI 配置")
async def update_ai_config(config: Dict[str, Any], llm_service: LLMService = Depends(get_llm_service)):
    try:
        current_ai_config = globals.service.config.get("ai", {})
        current_ai_config.update(config)
        
        success, message = globals.service.configuration_service.update_config({
            "ai": current_ai_config
        })
        
        if not success:
            raise HTTPException(status_code=500, detail=message)
        
        # 配置变更后重新加载 client
        await llm_service.reload_client()
        
        return {"message": "AI 配置更新成功", "config": current_ai_config}
    except Exception as e:
        log_audit("AI", "失败", f"更新 AI 配置失败: {e}", level="ERROR")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test-translation", summary="测试 AI 翻译")
async def test_translation(
    req: TranslationRequest,
    llm_service: LLMService = Depends(get_llm_service)
):
    try:
        result = await llm_service.translate(req.text, context=req.context, extra_info=req.extra_info)
        return {"original": req.text, "translated": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/batch-translate", summary="批量 AI 翻译")
async def batch_translate(
    req: BatchTranslationRequest,
    llm_service: LLMService = Depends(get_llm_service)
):
    """
    批量翻译一组短文本（如人名、角色名）。
    """
    if not req.texts:
        return {"results": []}
    
    if len(req.texts) > 50:
        raise HTTPException(status_code=400, detail="单次批量翻译不得超过 50 条")

    input_text = "\n".join([f"{i+1}. {t}" for i, t in enumerate(req.texts)])
    instruction = "请翻译以下列表。严格保持行数和编号一致，每行仅返回翻译结果。不要输出任何解释说明。"
    
    try:
        full_input = f"{instruction}\n\n待翻译列表：\n{input_text}"
        raw_result = await llm_service.translate(full_input, context=req.context, extra_info=req.extra_info)
        
        results = []
        lines = raw_result.split('\n')
        for line in lines:
            clean_line = re.sub(r'^\d+[\.、\s]+', '', line).strip()
            if clean_line:
                results.append(clean_line)
        
        if len(results) != len(req.texts):
            log_audit("AI", "处理", f"批量翻译解析数量不一致: 输入 {len(req.texts)}, 输出 {len(results)}", level="WARN")
            while len(results) < len(req.texts):
                results.append("")
            results = results[:len(req.texts)]

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
        # 如果解析数量不符，记录警告
        if len(results) != len(texts):
            log_audit("AI", "处理", f"批量翻译解析数量不一致: 输入 {len(texts)}, 输出 {len(results)}", level="WARN")
            # 补齐或截断以防前端崩溃
            while len(results) < len(texts):
                results.append("")
            results = results[:len(texts)]

        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chat", summary="AI 对话测试")
async def ai_chat(
    messages: List[Dict[str, str]], 
    llm_service: LLMService = Depends(get_llm_service)
):
    try:
        result = await llm_service.chat(messages)
        return {"response": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
