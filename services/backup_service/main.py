import logging
import sys
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse

# --- 路徑修正與模組匯入 ---
# 確保能夠從 services/backup_service/main.py 找到 src 下的模組
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# --- 常數與設定 ---
log = logging.getLogger(__name__)
# JULES: 建立一個獨立的 FastAPI app 實例
app = FastAPI(title="Backup Service")

# --- 背景任務函式 ---
def run_backup_task():
    """
    這是在背景執行的備份任務。
    這是從舊的 page5_backup.py 遷移過來的核心業務邏輯。
    """
    # --- 延遲導入 (Lazy Import) ---
    # 確保工具模組的路徑正確
    from tools.gdrive_backup import create_backup_archive, upload_to_google_drive

    log.info("[Backup Service] 背景任務：開始執行備份流程...")
    try:
        # 步驟 1: 建立壓縮檔
        archive_path = create_backup_archive()

        if not archive_path:
            raise RuntimeError("建立備份壓縮檔失敗。")

        # 步驟 2: 上傳到 Google Drive
        upload_url = upload_to_google_drive(archive_path)

        if not upload_url:
            raise RuntimeError("上傳檔案到 Google Drive 失敗。")

        log.info(f"[Backup Service] 背景任務：備份成功！檔案可在: {upload_url}")
        # 在真實應用中，可以將此 URL 透過 WebSocket 或其他方式通知主閘道

    except Exception as e:
        log.error(f"[Backup Service] 背景任務：備份流程中發生嚴重錯誤: {e}", exc_info=True)


# --- API 端點 ---
@app.post("/start_backup")
async def start_backup(background_tasks: BackgroundTasks):
    """
    觸發一個背景備份任務。
    """
    log.info("[Backup Service] API: 收到啟動備份的請求。")
    try:
        background_tasks.add_task(run_backup_task)
        return JSONResponse(
            status_code=202, # 202 Accepted: 請求已被接受處理，但尚未完成
            content={"message": "備份服務已成功接收請求並建立背景任務。"}
        )
    except Exception as e:
        log.error(f"[Backup Service] API: 啟動備份任務時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="備份服務啟動任務時發生伺服器內部錯誤。")

@app.get("/health")
async def health_check():
    """提供一個簡單的健康檢查端點。"""
    return {"status": "ok", "service": "Backup Service"}

# --- 主程式啟動 (用於獨立運行) ---
if __name__ == "__main__":
    import uvicorn

    # 設定基本的日誌記錄
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # JULES: 這裡應該有一個機制來註冊自己的埠號到服務註冊中心，
    # 但根據現有模式，這個啟動是由 orchestrator 處理的，所以這裡只提供一個標準的 uvicorn 啟動方式。
    uvicorn.run(app, host="0.0.0.0", port=8003) # 假設使用 8003 埠號
