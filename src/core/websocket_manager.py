# src/core/websocket_manager.py
import logging
from typing import List
from fastapi import WebSocket

log = logging.getLogger(__name__)

class ConnectionManager:
    """
    管理 WebSocket 連線的類別。
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受一個新的 WebSocket 連線。"""
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新的 WebSocket 連線已建立。目前連線數: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """斷開一個 WebSocket 連線。"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log.info(f"一個 WebSocket 連線已斷開。目前連線數: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """向所有已連線的客戶端廣播一條訊息。"""
        log.info(f"準備向 {len(self.active_connections)} 個客戶端廣播訊息: {message}")
        # 創建一個副本以避免在迭代時修改列表
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                # 如果傳送失敗（例如，客戶端已關閉），則移除此連線
                log.warning(f"傳送 WebSocket 訊息失敗: {e}。將移除此無效連線。")
                self.disconnect(connection)

# 建立一個全域的 ConnectionManager 實例，以便在整個應用程式中共享
manager = ConnectionManager()
