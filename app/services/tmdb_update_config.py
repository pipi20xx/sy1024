import json
import os
from pathlib import Path
from app.logger import logger, log_audit

CONFIG_FILE = Path(os.getenv("DATA_PATH", "data")) / "tmdb_update_config.json"

def load_config():
    if not CONFIG_FILE.exists():
        return {}
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log_audit("TMDB配置", "失败", f"加载 TMDB 更新配置失败: {e}", level="ERROR")
        return {}

def save_config(config: dict):
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        log_audit("TMDB配置", "失败", f"保存 TMDB 更新配置失败: {e}", level="ERROR")