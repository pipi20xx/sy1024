# app/websocket_manager.py

import json
import asyncio
from typing import List, Dict, Any
from fastapi import WebSocket, WebSocketDisconnect

from app.logger import log_audit

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self._log_queues: Dict[WebSocket, asyncio.Queue] = {}
        self._log_tasks: Dict[WebSocket, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

        # 订阅 LogBroadcaster
        from app.logger import LogBroadcaster
        queue = LogBroadcaster.subscribe()
        self._log_queues[websocket] = queue

        # 发送历史回填
        for log_msg in LogBroadcaster.get_history():
            try:
                await websocket.send_text(json.dumps({"type": "log", "data": log_msg}, ensure_ascii=False))
            except Exception:
                pass

        # 启动日志推送协程 (保存 task 引用，以便 disconnect 时取消)
        task = asyncio.create_task(self._log_forwarder(websocket, queue))
        self._log_tasks[websocket] = task
        log_audit("WebSocket", "连接", f"WebSocket 已连接，当前连接数: {len(self.active_connections)}", level="DEBUG")

    async def _log_forwarder(self, websocket: WebSocket, queue: asyncio.Queue):
        """从 LogBroadcaster 的 queue 中获取日志并推送到 WebSocket"""
        try:
            while True:
                log_entry = await queue.get()
                try:
                    payload = json.dumps({"type": "log", "data": log_entry}, ensure_ascii=False)
                    await websocket.send_text(payload)
                except Exception:
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        # 取消日志推送协程
        task = self._log_tasks.pop(websocket, None)
        if task and not task.done():
            task.cancel()

        # 取消订阅
        queue = self._log_queues.pop(websocket, None)
        if queue:
            from app.logger import LogBroadcaster
            LogBroadcaster.unsubscribe(queue)

        log_audit("WebSocket", "断开", f"WebSocket 已断开，剩余连接数: {len(self.active_connections)}", level="DEBUG")

    async def log_broadcast_loop(self):
        """
        兼容保留的空循环。
        日志推送已由 LogBroadcaster + _log_forwarder 接管，
        此方法仅作为心跳占位，防止外部调用报错。
        """
        while True:
            await asyncio.sleep(3600)

    async def broadcast(self, message: Dict[str, Any]):
        """
        Broadcasts a JSON message to all connected clients.
        """
        if not self.active_connections:
            return

        try:
            text_data = json.dumps(message, ensure_ascii=False)
        except Exception as e:
            log_audit("WebSocket", "广播", f"序列化广播消息失败: {e}", level="ERROR")
            return

        to_remove = []
        for connection in self.active_connections:
            try:
                await connection.send_text(text_data)
            except Exception:
                to_remove.append(connection)

        for ws in to_remove:
            self.disconnect(ws)

    async def broadcast_progress(self, task_type: str, status: str, current: int, total: int, message: str, extra: Dict = None):
        """
        Helper to broadcast standard progress events.
        """
        payload = {
            "type": "progress",
            "task": task_type,
            "data": {
                "status": status,
                "current": current,
                "total": total,
                "message": message,
                **(extra or {})
            }
        }
        await self.broadcast(payload)

# Global singleton instance
manager = ConnectionManager()
