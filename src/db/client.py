# db/client.py
#
# --- 說明 (由 Jules 於 2025-09-17 重構) ---
#
# 本檔案定義了與 DB Manager API 進行通訊的客戶端。
# 它已從原生的 socket 通訊升級為使用 httpx 函式庫，以實現更穩定、高效的 HTTP 通訊。
#
# httpx 客戶端會自動管理連線池與 HTTP Keep-Alive，
# 這意味著它可以在多個請求之間重複使用 TCP 連線，大幅減少延遲並提升效能。
#
import json
import logging
import os
import httpx

# --- 日誌設定 ---
log = logging.getLogger('DBClient')

class DBClient:
    """
    與 DB Manager API 進行通訊的 HTTP 客戶端。
    """
    def __init__(self, timeout: float = 60.0):
        """
        初始化客戶端。

        Args:
            timeout (float): 請求的預設超時時間（秒）。
        """
        import httpx
        self.port = self._get_server_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        # 初始化一個 httpx.Client 實例。
        # 這個 Client 物件會管理連線池，並在多個請求中重複使用連線。
        self._client = httpx.Client(base_url=self.base_url, timeout=timeout)
        log.info(f"DBClient 已初始化，將連線至 {self.base_url}")

    def _get_server_port(self) -> int:
        """
        從環境變數獲取 DB Manager 伺服器的埠號。
        這是為了與 orchestrator 的動態埠號分配機制相容。
        """
        port = int(os.getenv('DB_MANAGER_PORT', 50001)) # 保留預設值以防萬一
        log.info(f"讀取到 DB Manager 埠號: {port} ({'來自環境變數' if 'DB_MANAGER_PORT' in os.environ else '使用預設值'})")
        return port

    def _send_request(self, action: str, params: dict = None) -> dict:
        """
        一個私有的輔助方法，用於向 /execute 端點發送請求並接收回應。
        """
        if params is None:
            params = {}

        request_data = {
            "action": action,
            "params": params
        }

        try:
            # 使用 httpx Client 發送 POST 請求。
            # httpx 會自動處理 JSON 的序列化。
            response = self._client.post("/execute", json=request_data)

            # 檢查 HTTP 狀態碼。如果狀態碼是 4xx 或 5xx，此行會引發 httpx.HTTPStatusError。
            response.raise_for_status()

            # 解析 JSON 回應
            response_data = response.json()

            # 根據新的 API 格式，直接回傳 "data" 欄位的內容
            if response_data.get("status") == "success":
                return response_data.get("data")
            else:
                # 理論上 raise_for_status 已經處理了錯誤，但作為雙重保險
                error_message = response_data.get("detail", "API 回傳未知錯誤")
                log.error(f"API 在處理 action '{action}' 時回傳錯誤: {error_message}")
                raise RuntimeError(f"DB Manager API Error: {error_message}")

        except httpx.HTTPStatusError as e:
            # 捕獲 HTTP 錯誤（例如 404 Not Found, 500 Internal Server Error）
            # e.response.text 包含了伺服器返回的詳細錯誤訊息
            log.error(f"請求 action '{action}' 失敗，HTTP 狀態碼: {e.response.status_code}，伺服器回應: {e.response.text}")
            raise RuntimeError(f"HTTP Error {e.response.status_code}: {e.response.text}") from e
        except httpx.RequestError as e:
            # 捕獲網路層級的錯誤（例如連線被拒絕、DNS 查詢失敗）
            log.error(f"與 DB Manager API ({self.base_url}) 通訊時發生網路錯誤: {e}")
            raise ConnectionError(f"無法連線至 DB Manager API: {e}") from e
        except json.JSONDecodeError as e:
            log.error(f"無法解析來自伺服器的回應，可能不是有效的 JSON: {e}")
            raise ValueError("伺服器回應格式錯誤") from e


    # --- 公開 API 方法 ---
    # 這些方法的簽名和功能保持不變，它們的改動僅在於底層的 _send_request 實現。
    # 這確保了對外介面的穩定性。

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

    def get_all_analysis_tasks(self) -> list[dict]:
        return self._send_request("get_all_analysis_tasks")

    def create_or_get_analysis_task(self, file_id: int, filename: str) -> dict:
        return self._send_request("create_or_get_analysis_task", {"file_id": file_id, "filename": filename})

    def update_analysis_task(self, task_id: int, updates: dict) -> dict:
        return self._send_request("update_analysis_task", {"task_id": task_id, "updates": updates})

    def get_analysis_task(self, task_id: int) -> dict | None:
        return self._send_request("get_analysis_task", {"task_id": task_id})

    def get_performance_dashboard_data(self) -> list[dict]:
        """(V4 優化新增) 獲取儀表板數據。"""
        return self._send_request("get_performance_dashboard_data")

    def get_urls_by_hash(self, file_hash: str) -> list[dict]:
        return self._send_request("get_urls_by_hash", {"file_hash": file_hash})

    def get_analysis_task_by_file_id(self, file_id: int) -> dict | None:
        return self._send_request("get_analysis_task_by_file_id", {"file_id": file_id})

    def get_url_by_id(self, url_id: int) -> dict | None:
        return self._send_request("get_url_by_id", {"url_id": url_id})

    def update_url(self, url_id: int, updates: dict) -> bool:
        return self._send_request("update_url", {"url_id": url_id, "updates": updates})

    def get_urls_by_statuses(self, statuses: list[str]) -> list[dict]:
        """(V4 優化新增) 根據狀態列表獲取 URL 紀錄。"""
        return self._send_request("get_urls_by_statuses", {"statuses": statuses})

    def add_new_urls(self, parsed_data: list[dict], source_text: str) -> int:
        """(V4 優化新增) 新增 URL 紀錄，並進行去重。"""
        return self._send_request("add_new_urls", {"parsed_data": parsed_data, "source_text": source_text})

    def get_filtered_urls(self, start_date: str = None, end_date: str = None) -> list[dict]:
        """(V4 優化新增) 根據日期範圍獲取 URL 紀錄。"""
        return self._send_request("get_filtered_urls", {"start_date": start_date, "end_date": end_date})

    def get_urls_by_url_list(self, url_list: list[str]) -> list[dict]:
        """
        (Jules @ 2025-10-08) 新增：根據 URL 列表獲取詳細資訊。
        """
        return self._send_request("get_urls_by_url_list", {"url_list": url_list})

    def get_system_logs(self, levels: list[str] = None, sources: list[str] = None) -> list[dict]:
        return self._send_request("get_system_logs", {
            "levels": levels or [],
            "sources": sources or []
        })

    def find_dependent_task(self, parent_task_id: str) -> str | None:
        return self._send_request("find_dependent_task", {"parent_task_id": parent_task_id})

    def get_app_state(self, key: str) -> str | None:
        return self._send_request("get_app_state", {"key": key})

    def set_app_state(self, key: str, value: str) -> bool:
        return self._send_request("set_app_state", {"key": key, "value": value})

    def get_all_app_states(self) -> dict[str, str]:
        return self._send_request("get_all_app_states")

    def clear_all_tasks(self) -> bool:
        return self._send_request("clear_all_tasks")

    # --- (Jules @ 2025-10-12) 新增：工作流 (Workflow) 客戶端方法 ---
    def create_workflow(self, name: str) -> int:
        """建立一個新的工作流並回傳其 ID。"""
        return self._send_request("create_workflow", {"name": name})

    def add_workflow_step(self, workflow_id: int, step_order: int, command: str, parameters: dict) -> int:
        """在工作流中新增一個步驟。"""
        return self._send_request("add_workflow_step", {
            "workflow_id": workflow_id,
            "step_order": step_order,
            "command": command,
            "parameters": parameters
        })

    def get_workflow(self, workflow_id: int) -> dict | None:
        """獲取特定工作流的資訊。"""
        return self._send_request("get_workflow", {"workflow_id": workflow_id})

    def get_workflow_steps(self, workflow_id: int) -> list[dict]:
        """獲取一個工作流的所有步驟。"""
        return self._send_request("get_workflow_steps", {"workflow_id": workflow_id})

    def update_workflow_status(self, workflow_id: int, status: str) -> bool:
        """更新工作流的總體狀態。"""
        return self._send_request("update_workflow_status", {"workflow_id": workflow_id, "status": status})

    def update_workflow_step_status(self, step_id: int, status: str, result: dict = None, error_message: str = None) -> bool:
        """更新單一步驟的狀態。"""
        return self._send_request("update_workflow_step_status", {
            "step_id": step_id,
            "status": status,
            "result": result,
            "error_message": error_message
        })
    # --- 結束工作流方法 ---

# --- V4 計畫書優化 (2025-09-18) ---
#
# 移除了舊有的 get_client() 單例模式。
#
# 原因：
# 當使用 FastAPI 等現代化的依賴注入框架時，在模組級別維護一個全域單例物件
# 是一種反模式。它使得依賴關係變得隱晦，且難以進行單元測試。
#
# 正確的作法是：
# 1. 在應用程式的主進入點 (例如 api_server.py) 建立一個 DBClient 的實例。
# 2. 透過 FastAPI 的依賴注入系統 (Depends)，將這個共享的實例提供給所有需要它的 API 路由。
#
# 這樣做可以讓 FastAPI 來管理物件的生命週期，使程式碼更清晰、更易於維護和測試。
# 原本由 get_client() 提供的「正在建立一個新的 DBClient 實例...」日誌訊息，
# 現在應該只會在 api_server.py 啟動時出現一次，這才是預期的行為。
