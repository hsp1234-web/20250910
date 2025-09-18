# services/downloader_service/main.py
# 下載器微服務：一個用於處理檔案下載的獨立服務。
import os
import logging
import gdown
import filetype
import uuid
import requests
import re
import sys
from urllib.parse import urlparse
from pathlib import Path
from typing import Optional

# --- 依賴 ---
from fastapi import FastAPI, APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
import uvicorn
from datetime import datetime
import zoneinfo
from dateutil import parser as date_parser
from dateutil.parser import ParserError

# --- 設定與全域變數 ---
SERVICE_NAME = "DownloaderService"
OUTPUT_DIR = Path("/tmp/downloads") # 微服務將檔案下載到自己的暫存區
OUTPUT_DIR.mkdir(exist_ok=True)

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format=f'%(asctime)s - %(levelname)s - [{SERVICE_NAME}] - %(message)s'
)
log = logging.getLogger(__name__)


# --- 1. 輔助函式 (從 core 移植) ---

# from core.filename_utils
def sanitize_for_filename(text: str, max_length: Optional[int] = 50) -> str:
    if not text: return ""
    sanitized_text = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', text)
    sanitized_text = re.sub(r'__+', '_', sanitized_text)
    sanitized_text = sanitized_text.strip('_')
    if max_length is not None and len(sanitized_text) > max_length:
        sanitized_text = sanitized_text[:max_length]
        sanitized_text = sanitized_text.strip('_')
    return sanitized_text

# from core.time_utils
TAIPEI_TZ = zoneinfo.ZoneInfo("Asia/Taipei")
def format_iso_for_filename(iso_string: str) -> str:
    if not iso_string:
        return datetime.now(TAIPEI_TZ).strftime('%Y-%m-%dT%H-%M-%S')
    try:
        processed_string = iso_string.replace("上午", "AM").replace("下午", "PM")
        dt_object = date_parser.parse(processed_string)
        if dt_object.tzinfo is None:
            dt_object = dt_object.replace(tzinfo=TAIPEI_TZ)
        dt_taipei = dt_object.astimezone(TAIPEI_TZ)
        return dt_taipei.strftime('%Y-%m-%dT%H-%M-%S')
    except (ValueError, TypeError, ParserError) as e:
        log.warning(f"無法解析時間字串 '{iso_string}' ({e})。回退到使用當前時間。")
        return datetime.now(TAIPEI_TZ).strftime('%Y-%m-%dT%H-%M-%S')


# --- 2. 核心下載邏輯 (從 drive_downloader 移植) ---

def _get_extension_from_headers(url: str) -> Optional[str]:
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=10) as r:
            r.raise_for_status()
            content_disposition = r.headers.get('content-disposition')
            if content_disposition:
                filenames = re.findall('filename="(.+?)"', content_disposition)
                if filenames:
                    filename = filenames[0]
                    if "." in filename and len(filename.split('.')[-1]) < 10:
                         ext = f".{filename.split('.')[-1]}"
                         log.info(f"從 Content-Disposition 標頭中成功解析出副檔名: {ext}")
                         return ext
    except Exception as e:
        log.warning(f"從 headers 獲取檔名時發生錯誤: {e}")
    return None

def _get_extension_from_url_path(url: str) -> Optional[str]:
    try:
        path = urlparse(url).path
        ext = Path(path).suffix
        if ext and 1 < len(ext) <= 10:
            log.info(f"從 URL 路徑中成功解析出副檔名: {ext}")
            return ext
    except Exception as e:
        log.warning(f"從 URL 路徑解析副檔名時出錯: {e}")
    return None

def download_file_logic(
    url: str,
    url_id: int,
    author: Optional[str],
    message_date: Optional[str],
    message_time: Optional[str],
    output_dir_override: str
) -> str:
    """
    移植並修改後的核心下載邏輯。
    成功時回傳最終檔案路徑，失敗時引發例外。
    """
    output_dir = Path(output_dir_override)
    log.info(f"準備從 URL 下載：{url} (ID: {url_id}) 至 {output_dir}")
    temp_filename = f"temp_{uuid.uuid4()}"
    temp_path = output_dir / temp_filename

    try:
        extension = _get_extension_from_headers(url)
        gdown.download(url, str(temp_path), quiet=False, fuzzy=True)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            raise IOError(f"下載失敗：gdown 未建立有效的檔案。")

        if not extension:
            kind = filetype.guess(str(temp_path))
            if kind:
                extension = f".{kind.extension}"
            else:
                extension = _get_extension_from_url_path(url) or ""

        parts = [str(url_id)]
        if author: parts.append(sanitize_for_filename(author))
        if message_date and message_time:
            timestamp = format_iso_for_filename(f"{message_date}T{message_time}:00")
            parts.append(timestamp)

        final_filename = f"{'_'.join(parts)}{extension}"
        final_path = output_dir / final_filename
        temp_path.rename(final_path)

        log.info(f"✅ 檔案成功下載並命名為：{final_path}")
        return str(final_path)

    except Exception as e:
        log.error(f"❌ 下載過程中發生嚴重錯誤 (URL ID: {url_id}): {e}", exc_info=True)
        # 確保在發生錯誤時也清理暫存檔
        if temp_path.exists():
            temp_path.unlink()
        # 重新引發一個通用的例外，讓 API 端點可以捕獲
        raise RuntimeError(f"下載失敗: {e}")


# --- 3. API 路由 ---

router = APIRouter()

class DownloadPayload(BaseModel):
    url: str
    url_id: int
    output_dir: str # 新增：指定輸出目錄
    author: Optional[str] = None
    message_date: Optional[str] = None
    message_time: Optional[str] = None

@router.post("/download", summary="下載單一檔案")
async def handle_download(payload: DownloadPayload):
    """
    接收下載請求，執行下載邏輯，並回傳結果。
    現在會將檔案下載到由呼叫者指定的 output_dir。
    """
    try:
        # 確保指定的輸出目錄存在
        Path(payload.output_dir).mkdir(exist_ok=True, parents=True)

        downloaded_path = download_file_logic(
            url=payload.url,
            url_id=payload.url_id,
            author=payload.author,
            message_date=payload.message_date,
            message_time=payload.message_time,
            # 將指定的目錄傳遞給核心邏輯
            output_dir_override=payload.output_dir
        )
        return {"status": "success", "local_path": downloaded_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- 4. FastAPI 應用主體 ---

app = FastAPI(
    title=SERVICE_NAME,
    description="一個用於處理檔案下載的獨立微服務。",
    version="1.0.0"
)

app.include_router(router)

@app.get("/", summary="健康檢查端點")
def read_root():
    return {"status": f"{SERVICE_NAME} is running"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8002)) # 使用 8002 作為預設埠號
    log.info(f"將在 http://127.0.0.1:{port} 上啟動伺服器")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
