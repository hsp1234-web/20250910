# src/services/file_watcher_service.py
import logging
import time
import sys
import json
from pathlib import Path

import shutil

# 確保能從根目錄正確匯入
# 這在由 orchestrator 啟動時是標準作法
try:
    from src.db import database as db
except ImportError:
    # 如果直接執行此腳本進行測試，需要手動添加路徑
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.db import database as db

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger('FileWatcherService')

# --- 常數設定 ---
INCOMING_DIR = Path(__file__).parent.parent.parent / "downloads" / "incoming"
FINAL_AUDIO_DIR = Path(__file__).parent.parent.parent / "downloads" / "audio"

class DownloadHandler(FileSystemEventHandler):
    """
    一個處理檔案系統事件的處理器，專門處理新下載的檔案。
    """
    def on_created(self, event):
        """
        當在受監控目錄中建立新檔案時呼叫。
        """
        if event.is_directory:
            return  # 忽略目錄事件

        # 稍微等待，確保檔案已完全寫入，避免讀取不完整的檔案
        time.sleep(1)
        log.info(f"📥 偵測到新檔案: {event.src_path}")
        self.process_new_file(Path(event.src_path))

    def process_new_file(self, file_path: Path):
        """
        處理新偵測到的檔案，包含完整的資料庫互動和檔案操作邏輯。
        """
        log.info("--- process_new_file 函式已開始執行 ---")
        if not file_path.exists():
            log.warning(f"檔案 {file_path} 在處理前就消失了，可能已被移動或刪除。")
            return

        task_hash = file_path.stem
        log.info(f"從檔案路徑中提取到 Task Hash: {task_hash}")

        task_info = None  # 先初始化
        try:
            # 1. 根據 task_hash 查詢任務資訊
            task_info = db.get_task_status(task_hash)
            if not task_info:
                log.error(f"資料庫中找不到對應的任務，Task Hash: {task_hash}。將忽略此檔案。")
                # 考慮是否要刪除這個孤兒檔案
                # file_path.unlink()
                return

            log.info(f"從資料庫中找到任務: {task_info}")

            # 2. 從 payload 中解析出原始影片標題
            try:
                payload = json.loads(task_info.get("payload", "{}"))
                # yt-dlp 可能會提供標題，我們優先使用它
                original_title = payload.get("video_title", "Unknown_Title")
                # 清理檔名，移除不安全的字元
                safe_title = "".join(c for c in original_title if c.isalnum() or c in (' ', '_', '-')).rstrip()
            except (json.JSONDecodeError, AttributeError):
                log.warning(f"無法從任務 payload 中解析標題，將使用通用標題。Task Hash: {task_hash}")
                safe_title = f"download_{task_hash}" # 使用雜湊值作為備用標題

            # 3. 執行重新命名和移動邏輯
            final_filename = f"[m4a]{safe_title}{file_path.suffix}"
            # 在 rename 之前，再次確保目標目錄存在
            FINAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            final_path = FINAL_AUDIO_DIR / final_filename

            log.info(f"準備將檔案從 '{file_path}' 移動並重新命名為 '{final_path}'")
            # 使用 shutil.move 來提供最穩健的檔案移動/重新命名操作
            import shutil
            shutil.move(str(file_path), str(final_path))

            # 4. 更新資料庫中的任務狀態為 '已完成'
            result_payload = json.dumps({"output_path": str(final_path)})
            db.update_task_status(task_hash, "已完成", result=result_payload)
            log.info(f"✅ 成功處理並移動檔案。Task Hash: {task_hash}")

        except Exception as e:
            log.error(f"❌ 處理檔案 {file_path} 時發生未預期的錯誤: {e}", exc_info=True)
            if task_hash and task_info:
                # 5. 如果處理失敗，更新狀態為 'failed'
                error_message = json.dumps({"error": str(e), "traceback": repr(e)})
                db.update_task_status(task_hash, "failed", result=error_message)


def start_file_watcher_service():
    """
    啟動檔案監控服務。
    """
    # 確保監控目錄存在
    INCOMING_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"📂 檔案監控服務已啟動，正在監控目錄: {INCOMING_DIR}")

    event_handler = DownloadHandler()
    observer = Observer()
    observer.schedule(event_handler, str(INCOMING_DIR), recursive=False)
    observer.start()

    try:
        # 保持主執行緒存活，讓觀察者執行緒在背景運作
        while True:
            time.sleep(5) # 降低 CPU 使用率
    except KeyboardInterrupt:
        observer.stop()
        log.info("🛑 收到中斷訊號，檔案監控服務已停止。")
    except Exception as e:
        log.error(f"服務主迴圈發生錯誤: {e}", exc_info=True)
        observer.stop()

    observer.join()

if __name__ == "__main__":
    # 當直接執行此檔案時，啟動服務
    log.info("以獨立模式啟動檔案監控服務...")
    start_file_watcher_service()