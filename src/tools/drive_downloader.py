import os
import logging
import gdown
import filetype
import uuid
from datetime import datetime
from pathlib import Path
import sys

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from core.time_utils import format_iso_for_filename

def download_file(url: str, output_dir: str, url_id: int, created_at_str: str) -> str | None:
    """
    從指定的 URL (特別是 Google Drive) 智慧地檔案。
    - 會使用 filetype 函式庫來強制偵測檔案的副檔名。
    - 會使用傳入的 created_at 時間戳和 url_id 來建立統一的檔名。

    :param url: 檔案的 Google Drive 分享連結。
    :param output_dir: 儲存檔案的目錄。
    :param url_id: 該 URL 在資料庫中的 ID。
    :param created_at_str: 該 URL 在資料庫中的建立時間字串 (YYYY-MM-DD HH:MM:SS)。
    :return: 最終儲存的檔案路徑，或在失敗時回傳 None。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url} (ID: {url_id})")

    # 建立一個唯一的暫存檔名，避免衝突
    temp_filename = f"temp_{uuid.uuid4()}"
    temp_path = Path(output_dir) / temp_filename

    try:
        # 步驟 1: 下載檔案到暫存路徑
        gdown.download(url, str(temp_path), quiet=False, fuzzy=True)

        if not temp_path.exists() or temp_path.stat().st_size == 0:
            logging.error(f"❌ 下載失敗：gdown 執行完畢但未建立有效的檔案於 {temp_path}。")
            if temp_path.exists():
                temp_path.unlink() # 清理空的暫存檔
            return None

        # 步驟 2: 偵測檔案類型以取得正確的副檔名
        kind = filetype.guess(str(temp_path))
        if kind is None:
            logging.warning(f"無法偵測檔案類型：{url_id}。將不設定副檔名。")
            extension = ""
        else:
            extension = f".{kind.extension}"
            logging.info(f"偵測到檔案類型: {kind.mime} -> 副檔名: {extension}")

        # 步驟 3: 根據傳入的時間和 ID 建立最終檔名
        # 我們現在使用集中的時間工具來處理時間戳，確保時區正確
        timestamp = format_iso_for_filename(created_at_str)
        final_filename = f"{timestamp}_file_{url_id}{extension}"
        final_path = Path(output_dir) / final_filename

        # 步驟 4: 將暫存檔重新命名為最終檔名
        temp_path.rename(final_path)

        logging.info(f"✅ 檔案成功下載並命名為：{final_path}")
        return str(final_path)

    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤 (URL ID: {url_id}): {e}", exc_info=True)
        # 清理可能的殘留暫存檔
        if temp_path.exists():
            temp_path.unlink()
        return None
