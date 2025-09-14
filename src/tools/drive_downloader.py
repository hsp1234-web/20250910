import os
import logging
import gdown
import filetype
import uuid
import requests
import re
from pathlib import Path
import sys

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from core.time_utils import format_iso_for_filename
from core.filename_utils import sanitize_for_filename
from typing import Optional

def _get_extension_from_headers(url: str) -> Optional[str]:
    """嘗試從 HTTP headers 中獲取檔名和副檔名。"""
    try:
        with requests.get(url, stream=True, allow_redirects=True, timeout=10) as r:
            r.raise_for_status()
            content_disposition = r.headers.get('content-disposition')
            if content_disposition:
                # e.g., 'attachment; filename="example.docx"'
                filenames = re.findall('filename="(.+?)"', content_disposition)
                if filenames:
                    filename = filenames[0]
                    # 確保副檔名存在且小於 10 個字元
                    if "." in filename and len(filename.split('.')[-1]) < 10:
                         ext = f".{filename.split('.')[-1]}"
                         logging.info(f"從 Content-Disposition 標頭中成功解析出副檔名: {ext}")
                         return ext
    except Exception as e:
        logging.warning(f"從 headers 獲取檔名時發生錯誤: {e}")
    return None


def download_file(
    url: str,
    output_dir: str,
    url_id: int,
    author: Optional[str],
    message_date: Optional[str],
    message_time: Optional[str]
) -> Optional[str]:
    """
    從指定的 URL (特別是 Google Drive) 智慧地檔案。
    - 優先從 HTTP headers 獲取副檔名。
    - 若失敗，則使用 filetype 函式庫來偵測檔案的副檔名。
    - 檔名會根據條件式時間戳和作者資訊建立。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url} (ID: {url_id})")

    temp_filename = f"temp_{uuid.uuid4()}"
    temp_path = Path(output_dir) / temp_filename

    try:
        # 步驟 1: 預先獲取副檔名
        extension = _get_extension_from_headers(url)

        # 步驟 2: 下載檔案到暫存路徑
        gdown.download(url, str(temp_path), quiet=False, fuzzy=True)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            logging.error(f"❌ 下載失敗：gdown 執行完畢但未建立有效的檔案於 {temp_path}。")
            if temp_path.exists():
                temp_path.unlink()
            return None

        # 步驟 3: 如果從 headers 中未獲取到副檔名，則使用 filetype 作為備案
        if not extension:
            logging.info("無法從 headers 獲取副檔名，嘗試使用 filetype 進行內容偵測。")
            kind = filetype.guess(str(temp_path))
            if kind is None:
                logging.warning(f"無法偵測檔案類型：{url_id}。將不設定副檔名。")
                extension = ""
            else:
                extension = f".{kind.extension}"
                logging.info(f"filetype 偵測到檔案類型: {kind.mime} -> 副檔名: {extension}")

        # 步驟 4: 根據最終需求建立檔名
        parts = [str(url_id)]
        if author:
            sanitized_author = sanitize_for_filename(author)
            parts.append(sanitized_author)
        if message_date and message_time:
            source_timestamp_str = f"{message_date}T{message_time}:00"
            timestamp = format_iso_for_filename(source_timestamp_str)
            parts.append(timestamp)
            logging.info(f"使用 LINE 訊息時間 '{source_timestamp_str}' 產生檔名。")
        else:
            logging.info(f"無 LINE 訊息時間，檔名將不包含時間戳。")

        final_filename = f"{'_'.join(parts)}{extension}"
        final_path = Path(output_dir) / final_filename

        # 步驟 5: 將暫存檔重新命名為最終檔名
        temp_path.rename(final_path)

        logging.info(f"✅ 檔案成功下載並命名為：{final_path}")
        return str(final_path)

    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤 (URL ID: {url_id}): {e}", exc_info=True)
        if temp_path.exists():
            temp_path.unlink()
        return None
