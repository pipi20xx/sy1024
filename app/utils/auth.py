import os
import secrets
from datetime import datetime, timedelta
from typing import Optional
import bcrypt
from jose import jwt

# 加密配置
SECRET_KEY = None
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 默认登录有效期 24 小时

def get_jwt_secret_key():
    """获取JWT密钥，从配置文件读取或生成新的"""
    global SECRET_KEY
    if SECRET_KEY is None:
        from app.services.configuration import ConfigurationService
        config_service = ConfigurationService()
        config = config_service.get_config()
        
        SECRET_KEY = config.get("jwt_secret_key")
        
        if not SECRET_KEY:
            SECRET_KEY = secrets.token_urlsafe(32)
            config["jwt_secret_key"] = SECRET_KEY
            config_service._save_config_to_disk(config)
    
    return SECRET_KEY

def verify_password(plain_password: str, hashed_password: str):
    """校验明文密码与哈希值是否匹配"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def get_password_hash(password: str):
    """对明文密码进行加密"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None, permanent: bool = False):
    """创建 JWT 访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif permanent:
        expire = datetime.utcnow() + timedelta(days=365 * 10)  # 10年，相当于永久
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_jwt_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """解析并验证 JWT 令牌"""
    try:
        payload = jwt.decode(token, get_jwt_secret_key(), algorithms=[ALGORITHM])
        return payload
    except:
        return None

def verify_token_version(payload: dict, user_token_version: int) -> bool:
    """验证 Token 版本是否匹配"""
    token_version = payload.get("token_version")
    return token_version is not None and token_version == user_token_version
