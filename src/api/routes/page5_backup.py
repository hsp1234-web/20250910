import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- 背景任務函式 ---
def run_backup_task():
    """
    這是在背景執行的備份任務。
    """
    # --- 延遲導入 (Lazy Import) ---
    from tools.gdrive_backup import create_backup_archive, upload_to_google_drive

    log.info("背景任務：開始執行備份流程...")
    try:
        # 步驟 1: 建立壓縮檔
        archive_path = create_backup_archive()

        if not archive_path:
            raise RuntimeError("建立備份壓縮檔失敗。")

        # 步驟 2: 上傳到 Google Drive
        # 注意：此處的認證是一個複雜問題，目前僅為模擬
        upload_url = upload_to_google_drive(archive_path)

        if not upload_url:
            raise RuntimeError("上傳檔案到 Google Drive 失敗。")

        log.info(f"背景任務：備份成功！檔案可在: {upload_url}")
        # 在真實應用中，可以將此 URL 透過 WebSocket 或其他方式通知前端

    except Exception as e:
        log.error(f"背景任務：備份流程中發生嚴重錯誤: {e}", exc_info=True)


# --- API 端點 ---
@router.post("/start_backup")
async def start_backup(background_tasks: BackgroundTasks):
    """
    觸發一個背景備份任務。
    """
    log.info("API: 收到啟動備份的請求。")
    try:
        background_tasks.add_task(run_backup_task)
        return JSONResponse(
            status_code=202, # 202 Accepted: 請求已被接受處理，但尚未完成
            content={"message": "已成功建立背景備份任務。"}
        )
    except Exception as e:
        log.error(f"API: 啟動備份任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="啟動備份任務時發生伺服器內部錯誤。")
