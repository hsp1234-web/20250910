# db/manager.py
#
# --- 執行與管理說明 (由 Jules 於 2025-08-12 新增) ---
#
# **重要：** 此腳本不應該被直接執行。
#
# 本檔案定義了一個作為背景服務運行的 TCP 伺服器，負責管理所有資料庫操作。
# 為了避免因程序未被正確關閉而導致的資源衝突（即「殭屍程序」問題），
# 此服務的生命週期由 `circus` 程序管理器進行統一管理。
#
# **標準啟動方式：**
# 1. **透過 `run_tests.py`**：這是執行測試的標準方法。
#    `run_tests.py` 會自動處理以下所有步驟：
#      a. 清理舊的程序和檔案。
#      b. 使用 `circus` 啟動此 `db_manager` 和 `api_server`。
#      c. 執行 `pytest` 測試。
#      d. 在測試結束後，確保所有服務都被優雅關閉。
#
# 2. **手動啟動 (開發時)**：若需手動啟動，應使用 `circus`：
#    `python -m circus.circusd circus.ini`
#
# 透過 `run_tests.py` 或 `circus` 來管理，可以從根本上解決
# 因資源（埠號、資料庫檔案）被占用而導致的啟動失敗問題。
#
# --- 程式碼開始 ---
import socketserver
import json
import logging
import sqlite3
from pathlib import Path

# 讓此腳本可以存取上層目錄的 db.database 模組
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from db import database

# --- 日誌設定 ---
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger('DBManagerServer')

# --- 伺服器設定 ---
# 核心原則：PORT 必須設定為 0。
#
# 說明：
# 將 PORT 設定為 0，能讓作業系統動態地為此伺服器分配一個當下可用的埠號。
# 這是解決「Address already in use」錯誤的關鍵。
#
# 系統的 `orchestrator.py` (協調器) 被設計用來處理這種動態埠號分配。
# 其運作方式如下：
# 1. 啟動此 `db_manager` 伺服器。
# 2. 伺服器啟動後，會將作業系統分配的實際埠號透過標準輸出 (stdout) 印出。
#    (例如: "DB_MANAGER_PORT: 54321")
# 3. 協調器會捕獲這個輸出，從而得知要連線到哪個埠號。
#
# 警告：請勿將此處改為任何固定的埠號。這樣做會破壞服務發現機制，
# 並重新導致埠號衝突問題。
HOST, PORT = "127.0.0.1", 0

# --- 指令分派 ---
# 建立一個函式名稱與指令 action 的對應字典
# 這樣可以避免巨大的 if/elif/else 結構，也更安全
ACTION_MAP = {
    "initialize_database": database.initialize_database,
    "add_task": database.add_task,
    "fetch_and_lock_task": database.fetch_and_lock_task,
    "update_task_progress": database.update_task_progress,
    "update_task_status": database.update_task_status,
    "get_task_status": database.get_task_status,
    "are_tasks_active": database.are_tasks_active,
    "get_all_tasks": database.get_all_tasks,
    "get_system_logs": database.get_system_logs_by_filter,
    "find_dependent_task": database.find_dependent_task,
    # JULES'S NEW FEATURE: Add app state actions
    "get_app_state": database.get_app_state,
    "set_app_state": database.set_app_state,
    "get_all_app_states": database.get_all_app_states,

    # --- AI 分析任務 (Analysis Tasks) Actions ---
    "create_or_get_analysis_task": database.create_or_get_analysis_task,
    "update_analysis_task": database.update_analysis_task,
    "get_all_analysis_tasks": database.get_all_analysis_tasks,
    "get_analysis_task": database.get_analysis_task,
    "get_urls_by_hash": database.get_urls_by_hash,
    "get_analysis_task_by_file_id": database.get_analysis_task_by_file_id,

    # --- extracted_urls Actions (2025-09-13) ---
    "get_url_by_id": database.get_url_by_id,
    "update_url": database.update_url,

    # For testing:
    "clear_all_tasks": database.clear_all_tasks,
}


class DBRequestHandler(socketserver.BaseRequestHandler):
    """
    處理來自客戶端請求的處理器。
    每個連線都會建立一個此類別的實例。
    """
    def handle(self):
        log.info(f"來自 {self.client_address} 的新連線。")
        try:
            while True:
                # 接收資料的長度 (4-byte header)
                header = self.request.recv(4)
                if not header:
                    break # 連線已關閉

                data_len = int.from_bytes(header, 'big')

                # 根據長度接收完整的資料
                data = self.request.recv(data_len)
                if not data:
                    break

                request = json.loads(data.decode('utf-8'))
                log.info(f"收到請求: {request}")

                action = request.get("action")
                params = request.get("params", {})

                response = {}
                try:
                    if action in ACTION_MAP:
                        # 從字典中獲取對應的函式
                        func = ACTION_MAP[action]

                        # 呼叫函式並傳入參數
                        result = func(**params)

                        response["status"] = "success"
                        response["data"] = result
                    else:
                        response["status"] = "error"
                        response["message"] = f"未知的 action: {action}"
                        log.warning(f"收到了未知的 action: {action}")

                except Exception as e:
                    log.error(f"執行 action '{action}' 時發生錯誤: {e}", exc_info=True)
                    response["status"] = "error"
                    # 將例外轉為字串，以便序列化
                    response["message"] = f"執行 '{action}' 時發生內部錯誤: {str(e)}"

                # 將回應序列化並發送回客戶端
                response_bytes = json.dumps(response).encode('utf-8')
                response_header = len(response_bytes).to_bytes(4, 'big')

                self.request.sendall(response_header + response_bytes)

        except ConnectionResetError:
            log.warning(f"客戶端 {self.client_address} 強制中斷了連線。")
        except Exception as e:
            log.error(f"處理連線 {self.client_address} 時發生未預期的錯誤: {e}", exc_info=True)
        finally:
            log.info(f"連線 {self.client_address} 已關閉。")


def run_server():
    """
    啟動資料庫管理者伺服器。
    """
    # 在伺服器啟動前，先主動清理任何可能存在的舊 port 檔案，確保一致性
    port_file = Path(__file__).parent / "db_manager.port"
    if port_file.exists():
        try:
            port_file.unlink()
            log.info(f"已成功移除舊的埠號檔案: {port_file}")
        except OSError as e:
            # 即便移除失敗，也只記錄錯誤，不中斷啟動流程
            log.error(f"無法移除舊的埠號檔案: {e}", exc_info=True)

    # 這是整個系統中，唯一應該呼叫 `initialize_database` 的地方
    try:
        log.info("資料庫管理者伺服器啟動前，正在進行資料庫初始化...")
        database.initialize_database()
        log.info("✅ 資料庫初始化成功。")
    except sqlite3.Error as e:
        log.critical(f"❌ 資料庫初始化失敗，伺服器無法啟動: {e}")
        # 在這種嚴重錯誤下，我們應該讓程序以非零代碼退出
        sys.exit(1)

    # 建立 TCP 伺服器
    # 讓 server 在程式結束後可以立即重用同一個位址
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((HOST, PORT), DBRequestHandler) as server:
        # 獲取實際綁定的埠號
        actual_port = server.server_address[1]
        log.info(f"🚀 資料庫管理者伺服器已在 {HOST}:{actual_port} 上啟動...")

        # JULES'S FIX (2025-08-31): 將選擇的埠號輸出，以便協調器可以讀取
        print(f"DB_MANAGER_PORT: {actual_port}", flush=True)
        # JULES'S FIX (2025-08-30): 發送明確的就緒信號，解決 orchestrator 的競爭條件問題
        # 這個信號必須在埠號被印出之後發送
        print("DB_MANAGER_READY", flush=True)

        try:
            # 啟動伺服器，它將一直運行直到被中斷 (例如 Ctrl+C)
            server.serve_forever()
        finally:
            log.info("伺服器已關閉。")


if __name__ == "__main__":
    run_server()
