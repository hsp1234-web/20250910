# db/client.py
import socket
import json
import logging
import time
import os
from pathlib import Path

# --- 日誌設定 ---
log = logging.getLogger('DBClient')

# --- 客戶端設定 ---
PORT_FILE = Path(__file__).parent / "db_manager.port"
RETRY_TIMEOUT = 10  # 秒

class DBClient:
    """
    與 DBManagerServer 進行通訊的客戶端。
    """
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = self._get_server_port()

    def _get_server_port(self) -> int:
        """
        從環境變數或預設值獲取資料庫管理者伺服器的埠號。
        """
        # JULES'S FIX (2025-08-31): 從環境變數讀取埠號，以支援動態埠號
        port = int(os.getenv('DB_MANAGER_PORT', 49999))
        log.info(f"使用 DB Manager 埠號: {port} ({'來自環境變數' if 'DB_MANAGER_PORT' in os.environ else '預設值'})")
        return port

    def _send_request(self, action: str, params: dict = None) -> dict:
        """
        一個私有的輔助方法，用於發送請求並接收回應。
        """
        if params is None:
            params = {}

        request_data = {
            "action": action,
            "params": params
        }

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.connect((self.host, self.port))

                # 序列化請求並發送
                request_bytes = json.dumps(request_data).encode('utf-8')
                request_header = len(request_bytes).to_bytes(4, 'big')
                sock.sendall(request_header + request_bytes)

                # 接收回應
                response_header = sock.recv(4)
                if not response_header:
                    raise ConnectionError("與伺服器的連線已中斷，未能收到回應標頭。")

                response_len = int.from_bytes(response_header, 'big')

                # --- JULES' FIX: Loop to receive all data ---
                response_chunks = []
                bytes_received = 0
                while bytes_received < response_len:
                    chunk = sock.recv(min(response_len - bytes_received, 4096))
                    if not chunk:
                        raise ConnectionError("與伺服器的連線已中斷，資料接收不完整。")
                    response_chunks.append(chunk)
                    bytes_received += len(chunk)

                response_bytes = b"".join(response_chunks)
                # --- END FIX ---

                response = json.loads(response_bytes.decode('utf-8'))

                # 檢查回應狀態
                if response.get("status") == "error":
                    error_message = response.get("message", "未知錯誤")
                    log.error(f"伺服器在處理 action '{action}' 時回傳錯誤: {error_message}")
                    # 根據需求，可以選擇拋出一個例外
                    raise RuntimeError(f"DB Manager Server Error: {error_message}")

                return response.get("data")

        except ConnectionRefusedError:
            log.error(f"連線被拒絕。請確保 DB 管理者伺服器正在 {self.host}:{self.port} 上運行。")
            raise
        except Exception as e:
            log.error(f"與 DB 管理者伺服器通訊時發生未預期錯誤: {e}", exc_info=True)
            raise

    # --- 公開 API 方法 ---
    # 這些方法模仿了 db/database.py 中的函式簽名，
    # 使得從舊的直接呼叫模式遷移到新的客戶端模式變得非常簡單。

    def add_task(self, task_id: str, payload: str, task_type: str = 'transcribe', depends_on: str = None) -> bool:
        return self._send_request("add_task", {
            "task_id": task_id,
            "payload": payload,
            "task_type": task_type,
            "depends_on": depends_on
        })

    def fetch_and_lock_task(self) -> dict | None:
        return self._send_request("fetch_and_lock_task")

    def update_task_progress(self, task_id: str, progress: int, partial_result: str):
        return self._send_request("update_task_progress", {
            "task_id": task_id,
            "progress": progress,
            "partial_result": partial_result
        })

    def update_task_status(self, task_id: str, status: str, result: str = None):
        return self._send_request("update_task_status", {
            "task_id": task_id,
            "status": status,
            "result": result
        })

    def get_task_status(self, task_id: str) -> dict | None:
        return self._send_request("get_task_status", {"task_id": task_id})

    def are_tasks_active(self) -> bool:
        return self._send_request("are_tasks_active")

    def get_all_tasks(self) -> list[dict]:
        return self._send_request("get_all_tasks")

    def get_system_logs(self, levels: list[str] = None, sources: list[str] = None) -> list[dict]:
        """
        從資料庫獲取系統日誌，可選擇性地按等級和來源篩選。
        """
        return self._send_request("get_system_logs", {
            "levels": levels or [],
            "sources": sources or []
        })

    def find_dependent_task(self, parent_task_id: str) -> str | None:
        """
        尋找依賴於某個父任務的任務。
        """
        return self._send_request("find_dependent_task", {"parent_task_id": parent_task_id})

    # JULES'S NEW FEATURE: App State methods
    def get_app_state(self, key: str) -> str | None:
        """
        從資料庫獲取一個應用程式狀態值。
        """
        return self._send_request("get_app_state", {"key": key})

    def set_app_state(self, key: str, value: str) -> bool:
        """
        在資料庫中設定一個應用程式狀態值。
        """
        return self._send_request("set_app_state", {"key": key, "value": value})

    def get_all_app_states(self) -> dict[str, str]:
        """
        從資料庫獲取所有應用程式狀態值。
        """
        return self._send_request("get_all_app_states")

    def clear_all_tasks(self) -> bool:
        """
        [僅供測試] 清空資料庫中的所有任務。
        """
        return self._send_request("clear_all_tasks")

# 可選：提供一個簡單的方式來獲取客戶端實例
_client_instance = None

def get_client():
    """
    提供一個單例的 DBClient 實例。
    """
    global _client_instance
    if _client_instance is None:
        log.info("正在建立一個新的 DBClient 實例...")
        _client_instance = DBClient()
    return _client_instance
