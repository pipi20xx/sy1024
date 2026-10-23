"""
数据库迁移脚本：创建 sessions 表
运行方式：python app/migrations/create_sessions_table.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import sessions_engine
from app.models.session import Base


async def migrate():
    """创建 sessions 表"""
    async with sessions_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        print("✓ 成功创建 sessions 表")


if __name__ == "__main__":
    print("开始数据库迁移...")
    asyncio.run(migrate())
    print("迁移完成！")
