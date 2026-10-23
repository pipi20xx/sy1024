from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base

# 注意：这里我们使用独立的 Base，避免与其他模块（如 models.py）冲突，
# 或者如果所有模型共享同一个 metadata，可以从 common 导入 Base。
# 但鉴于目前的结构，我们在此处定义一个简单的 Base 用于 user，因为它是独立的 users.db
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(100))
    is_active = Column(Boolean, default=True)
    otp_secret = Column(String(32), nullable=True)
    is_otp_enabled = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    token_version = Column(Integer, default=1)
