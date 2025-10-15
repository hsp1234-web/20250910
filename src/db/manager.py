# db/manager.py
#
# --- 執行與管理說明 (由 Jules 於 2025-09-17 重構) ---
#
# **重要：** 此腳本不應該被直接執行。
#
# 本檔案現在定義了一個基於 FastAPI 的 HTTP/ASGI 伺服器，負責管理所有資料庫操作。
# 它取代了原有的 raw socket 伺服器，以提供更穩定、更標準化的通訊。
#
# **標準啟動方式：**
# 此服務的生命週期應由 `orchestrator.py` 或類似的程序管理器進行統一管理。
# 正確的啟動指令是透過 Uvicorn：
#
# uvicorn src.db.manager:app --host 127.0.0.1 --port <PORT>
#
# 這種方式提供了高效能的非同步處理能力，並徹底解決了舊版實作中資料傳輸被截斷的問題。
#
# --- 程式碼開始 ---
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Dict, Any

# --- FastAPI 與 Pydantic 依賴 ---
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# 讓此腳本可以存取上層目錄的 db.database 模組
sys.path.append(str(Path(__file__).resolve().parent.parent))

from db import database

# --- 日誌設定 ---
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
log = logging.getLogger('DBManagerAPI')

# --- 指令分派 ---
# 建立一個函式名稱與指令 action 的對應字典
# 這個對應表維持不變，因為業務邏輯本身沒有改變
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
    "get_performance_dashboard_data": database.get_performance_dashboard_data, # V4 優化 (2025-09-18)
    "get_urls_by_hash": database.get_urls_by_hash,
    "get_analysis_task_by_file_id": database.get_analysis_task_by_file_id,

    # --- extracted_urls Actions (2025-09-13) ---
    "get_url_by_id": database.get_url_by_id,
    "update_url": database.update_url,
    "get_urls_by_statuses": database.get_urls_by_statuses, # V4 優化 (2025-09-18)
    "add_new_urls": database.add_new_urls, # V4 優化 (2025-09-18)
    "get_filtered_urls": database.get_filtered_urls, # V4 優化 (2025-09-18)
    "get_urls_by_url_list": database.get_urls_by_url_list, # (Jules @ 2025-10-08) 新增

    # --- 工作流引擎 Actions (Jules @ 2025-10-12) ---
    "create_workflow": database.create_workflow,
    "add_workflow_step": database.add_workflow_step,
    "get_workflow": database.get_workflow,
    "get_workflow_steps": database.get_workflow_steps,
    "update_workflow_status": database.update_workflow_status,
    "update_workflow_step_status": database.update_workflow_step_status,
    "get_all_workflows": database.get_all_workflows, # (Jules @ 2025-10-15) 新增
    "get_latest_workflow": database.get_latest_workflow, # (Jules @ 2025-10-15) 新增
    "reset_workflow": database.reset_workflow, # (Jules @ 2025-10-15) 新增
    # --- 結束 ---

    # For testing:
    "clear_all_tasks": database.clear_all_tasks,
}

# --- API 模型定義 ---

class DBRequest(BaseModel):
    """
    定義客戶端發送請求時的資料結構。
    使用 Pydantic 模型可以確保收到的資料型別正確。
    """
    action: str
    params: Dict[str, Any] = {}

# --- FastAPI 應用程式建立 ---

app = FastAPI(
    title="核心資料庫管理器 (Core DB Manager)",
    description="此 API 負責處理所有與系統核心資料庫 (SQLite) 的互動。",
    version="3.0.0"
)

@app.on_event("startup")
def on_startup():
    """
    在 FastAPI 伺服器啟動時執行的初始化程序。
    """
    log.info("資料庫管理器 API 啟動中...")
    try:
        log.info("正在進行資料庫初始化...")
        database.initialize_database()
        log.info("✅ 資料庫初始化成功。")
    except sqlite3.Error as e:
        log.critical(f"❌ 資料庫初始化失敗，伺服器無法啟動: {e}")
        # 在嚴重錯誤下，讓程序以非零代碼退出
        sys.exit(1)
    log.info("🚀 資料庫管理器 API 已成功啟動並準備就緒。")


@app.post("/execute", summary="執行資料庫操作")
def execute(request: DBRequest):
    """
    接收所有資料庫操作請求的核心端點。

    - **action**: 要執行的操作名稱，必須對應到 `ACTION_MAP` 中的一個鍵。
    - **params**: 一個包含該操作所需參數的字典。

    返回一個包含 `status` 和 `data` (成功時) 或 `detail` (失敗時) 的 JSON 物件。
    """
    action = request.action
    params = request.params
    log.info(f"收到 API 請求: action='{action}'")

    try:
        if action in ACTION_MAP:
            # 從字典中獲取對應的函式
            func = ACTION_MAP[action]

            # 呼叫函式並傳入參數
            result = func(**params)

            return {"status": "success", "data": result}
        else:
            log.warning(f"收到了未知的 action: {action}")
            raise HTTPException(status_code=404, detail=f"未知的 action: {action}")

    except HTTPException:
        # 如果是已知的 HTTP 錯誤，直接重新引發
        raise
    except Exception as e:
        log.error(f"執行 action '{action}' 時發生內部錯誤: {e}", exc_info=True)
        # 對於所有其他未預期的錯誤，返回 500 內部伺服器錯誤
        raise HTTPException(status_code=500, detail=f"執行 '{action}' 時發生內部錯誤: {str(e)}")

@app.get("/health", summary="健康檢查端點")
def health_check():
    """
    一個簡單的健康檢查端點，用於確認服務是否正在運行。
    可用於負載平衡器或系統監控。
    """
    return {"status": "ok", "message": "DB Manager API is running."}

# 注意：舊的 `if __name__ == "__main__":` 區塊已被移除。
# 此應用程式應由 Uvicorn 等 ASGI 伺服器來啟動。
