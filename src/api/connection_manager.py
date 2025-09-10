import logging
from fastapi import WebSocket
from typing import List

log = logging.getLogger(__name__)

class ConnectionManager:
    """
    管理 WebSocket 連線的中央元件。
    此類別處理連線的建立、中斷，並提供廣播訊息給所有用戶端的方法。
    """
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """接受一個新的 WebSocket 連線並將其加入到活動連線池中。"""
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線。目前共 {len(self.active_connections)} 個連線。")

    def disconnect(self, websocket: WebSocket):
        """從活動連線池中移除一個已中斷的 WebSocket 連線。"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            log.info(f"一個用戶端離線。目前共 {len(self.active_connections)} 個連線。")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """傳送私人訊息給指定的 WebSocket 用戶端。"""
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """將文字訊息廣播給所有已連線的用戶端。"""
        for connection in self.active_connections:
            await connection.send_text(message)

    async def broadcast_json(self, data: dict):
        """將 JSON 物件（字典）廣播給所有已連線的用戶端。"""
        # 建立一個副本以避免在疊代過程中修改列表
        for connection in self.active_connections[:]:
            try:
                await connection.send_json(data)
            except Exception as e:
                log.warning(f"傳送 WebSocket JSON 訊息時發生錯誤: {e}。可能用戶端已離線，將其移除。")
                self.disconnect(connection)

# 建立一個全域的單例 (singleton) 實例，供應用程式各處使用。
manager = ConnectionManager()
