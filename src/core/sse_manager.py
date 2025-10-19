# src/core/sse_manager.py
import asyncio
import logging
from collections import defaultdict

# --- 日誌設定 ---
log = logging.getLogger('SSEManager')

class SSEManager:
    """
    一個用於管理 Server-Sent Events (SSE) 連線和訊息廣播的類別。
    它允許按主題（例如 task_hash）進行廣播。
    """
    def __init__(self):
        # 使用 defaultdict 可以讓 self.channels[topic] 在主題首次出現時自動建立一個佇列
        self.channels: dict[str, list] = defaultdict(list)

    async def subscribe(self, topic: str):
        """
        一個非同步生成器，用於訂閱特定主題的訊息。
        客戶端可以透過這個生成器來接收即時更新。
        """
        q = asyncio.Queue()
        self.channels[topic].append(q)
        log.info(f"📬 新的訂閱者已加入主題: {topic} (目前共 {len(self.channels[topic])} 個訂閱者)")
        try:
            while True:
                # 等待佇列中的新訊息
                data = await q.get()
                yield data
        finally:
            # 當客戶端斷開連線時，從列表中移除它的佇列
            self.channels[topic].remove(q)
            log.info(f"📪 一個訂閱者已離開主題: {topic} (剩下 {len(self.channels[topic])} 個訂閱者)")

    async def publish(self, topic: str, message: str):
        """
        向特定主題的所有訂閱者發布一條訊息。
        """
        if topic in self.channels:
            log.info(f"📤 正在向主題 '{topic}' 發布訊息: {message}")
            # 使用 asyncio.gather 來並行地將訊息放入所有訂閱者的佇列中
            await asyncio.gather(*[q.put(message) for q in self.channels[topic]])

# 建立一個全域的單例，以便在應用程式的任何地方都可以使用
sse_manager = SSEManager()