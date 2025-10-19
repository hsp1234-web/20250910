# src/tools/youtube_downloader.py
import logging
import sys
import subprocess
import json
import shutil
from pathlib import Path

# 確保能從根目錄正確匯入
try:
    from src.db import database as db
except ImportError:
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.db import database as db

# --- 日誌設定 ---
log = logging.getLogger('YoutubeDownloaderTool')

# --- 常數設定 ---
DOWNLOAD_TIMEOUT_SECONDS = 1800  # 30 分鐘
INCOMING_DIR = Path("downloads/incoming")
FINAL_AUDIO_DIR = Path("downloads/audio")

import asyncio
from src.core.sse_manager import sse_manager

async def publish_sse_update(topic: str, status: str, message: str, **kwargs):
    """一個輔助函式，用於格式化並發布 SSE 訊息。"""
    payload = {"status": status, "message": message, **kwargs}
    await sse_manager.publish(topic, json.dumps(payload))

async def execute_full_download_workflow(task: dict):
    """
    一個完整的、自包含的下載工作流函式 (非同步版本)。
    它接收一個任務字典，並處理從下載到最終狀態更新的所有步驟。
    """
    task_hash = task.get("task_hash")
    payload_str = task.get("payload", "{}")

    if not task_hash:
        log.error("任務字典中缺少 'task_hash'，無法處理。")
        return

    try:
        payload = json.loads(payload_str)
        url = payload.get("original_url")
        if not url:
            raise ValueError("任務 payload 中缺少 'original_url'")

        await publish_sse_update(task_hash, "processing", "開始執行完整下載工作流...")
        log.info(f"[{task_hash}] 開始執行完整下載工作流。URL: {url}")

        # --- 步驟 1: 執行 yt-dlp 下載 ---
        INCOMING_DIR.mkdir(parents=True, exist_ok=True)
        temp_output_template = str(INCOMING_DIR / f"{task_hash}.%(ext)s")
        command = [
            sys.executable, "-m", "yt_dlp", "--print-json",
            "-f", "bestaudio[ext=m4a]/bestaudio", "-x", "--audio-format", "m4a",
            "--quiet", "--no-part", "--fragment-retries", "infinite",
            "-o", temp_output_template, url
        ]

        await publish_sse_update(task_hash, "processing", "正在執行 yt-dlp 指令...")
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: subprocess.run(
                command, capture_output=True, text=True, check=True,
                encoding='utf-8', timeout=DOWNLOAD_TIMEOUT_SECONDS
            )
        )

        # --- 步驟 2: 解析結果並找到下載的檔案 ---
        await publish_sse_update(task_hash, "processing", "下載完成，正在解析檔案資訊...")
        video_info = json.loads(result.stdout)
        downloaded_filepath_str = video_info.get("requested_downloads", [{}])[-1].get("filepath")
        if not downloaded_filepath_str:
            raise FileNotFoundError("yt-dlp 的輸出中找不到最終檔案路徑。")

        temp_file_path = Path(downloaded_filepath_str)
        if not temp_file_path.exists():
            raise FileNotFoundError(f"下載完成後，找不到預期的暫存檔案: {temp_file_path}")
        log.info(f"[{task_hash}] 檔案已成功下載至暫存位置: {temp_file_path}")

        # --- 步驟 3: 重新命名與移動 ---
        await publish_sse_update(task_hash, "processing", "準備重新命名並移動檔案...")
        original_title = video_info.get("title", "Unknown_Title")
        safe_title = "".join(c for c in original_title if c.isalnum() or c in (' ', '_', '-')).rstrip()
        final_filename = f"[m4a]{safe_title}{temp_file_path.suffix}"

        FINAL_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        final_path = FINAL_AUDIO_DIR / final_filename

        shutil.move(str(temp_file_path), str(final_path))
        log.info(f"[{task_hash}] 成功移動檔案至: {final_path}")

        # --- 步驟 4: 更新資料庫並發送最終成功訊息 ---
        result_payload = {
            "output_path": str(final_path),
            "original_title": original_title,
            "duration": video_info.get("duration", 0)
        }
        db.update_task_status(task_hash, "已完成", result=json.dumps(result_payload))
        await publish_sse_update(task_hash, "completed", "✅ 工作流成功完成！", data=result_payload)

        log.info(f"✅ [{task_hash}] 工作流成功完成！")

    except Exception as e:
        error_message = f"處理過程中發生未預期的錯誤: {str(e)}"
        log.error(f"[{task_hash}] {error_message}", exc_info=True)
        db.update_task_status(task_hash, "failed", result=json.dumps({"error": error_message}))
        await publish_sse_update(task_hash, "failed", error_message)