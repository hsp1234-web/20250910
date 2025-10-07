# -*- coding: utf-8 -*-
"""
任務管理模組
==============

(由 Jules 於 2025-10-08 根據計畫 15-4a 建立)

本模組提供一個名為 TaskManager 的類別，用於在記憶體中追蹤非同步背景任務的狀態。
這對於需要向前端回報進度的長時間執行操作（如下載、分析）至關重要。

核心功能:
- **任務創建**: 為一組項目產生唯一的任務 ID。
- **狀態追蹤**: 記錄整個任務以及其中每個子項目的狀態（例如，等待中、處理中、已完成、失敗）。
- **線程安全**: 使用 threading.Lock 來確保在多線程環境下（例如 FastAPI 背景任務）對任務字典的存取是安全的。

設計考量:
- **記憶體儲存**: 任務狀態被儲存在一個 Python 字典中。這意味著如果應用程式重新啟動，所有進行中的任務狀態都將遺失。
  對於當前的下載需求來說，這是一個可接受的權衡，因為前端可以簡單地重新發起下載請求。
- **單例模式**: 提供一個 get_manager() 函式來回傳 TaskManager 的單一實例，確保整個應用程式共享同一個任務狀態儲存。
"""

import uuid
import threading
from typing import Dict, Any, List

class TaskManager:
    """管理背景任務狀態的類別。"""

    def __init__(self):
        """初始化 TaskManager。"""
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_task(self, item_ids: List[int]) -> str:
        """
        為給定的項目 ID 列表創建一個新的下載任務。

        Args:
            item_ids (List[int]): 需要處理的項目 ID 列表。

        Returns:
            str: 新創建任務的唯一 task_id。
        """
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "status": "PROCESSING",
                "items": {
                    item_id: {
                        "id": item_id,
                        "title": "正在查詢...",
                        "author": "N/A",
                        "message_date": "N/A",
                        "message_time": "N/A",
                        "status": "WAITING",
                        "error_message": None
                    } for item_id in item_ids
                }
            }
        return task_id

    def get_task_status(self, task_id: str) -> Dict[str, Any] | None:
        """
        獲取指定任務的當前狀態。

        Args:
            task_id (str): 要查詢的任務 ID。

        Returns:
            Dict[str, Any] | None: 任務的狀態字典，如果找不到任務則回傳 None。
        """
        with self._lock:
            return self._tasks.get(task_id)

    def update_item_status(self, task_id: str, item_id: int, status: str, details: Dict[str, Any] = None):
        """
        更新任務中特定項目的狀態和詳細資訊。

        Args:
            task_id (str): 任務的 ID。
            item_id (int): 要更新的項目的 ID。
            status (str): 新的狀態 (例如 'DOWNLOADING', 'DOWNLOADED', 'FAILED')。
            details (Dict[str, Any], optional): 一個包含要更新的額外欄位的字典
                                                 (例如 'title', 'author', 'error_message')。
        """
        with self._lock:
            if task_id in self._tasks and item_id in self._tasks[task_id]["items"]:
                item = self._tasks[task_id]["items"][item_id]
                item["status"] = status
                if details:
                    item.update(details)

    def complete_task(self, task_id: str):
        """
        將整個任務的狀態標記為已完成。

        Args:
            task_id (str): 要完成的任務的 ID。
        """
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id]['status'] = 'COMPLETED'


# --- 單例模式 ---
_manager_instance = None
_manager_lock = threading.Lock()

def get_manager() -> TaskManager:
    """
    獲取 TaskManager 的單一實例。
    使用雙重檢查鎖定模式確保線程安全。
    """
    global _manager_instance
    if _manager_instance is None:
        with _manager_lock:
            if _manager_instance is None:
                _manager_instance = TaskManager()
    return _manager_instance