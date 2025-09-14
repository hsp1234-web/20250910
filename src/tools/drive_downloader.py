import os
import logging
import gdown
import uuid
import re
from pathlib import Path
import sys
import shutil

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from core.time_utils import format_iso_for_filename
from core.filename_utils import sanitize_for_filename
from typing import Optional

def download_file(
    url: str,
    output_dir: str,
    url_id: int,
    author: Optional[str],
    message_date: Optional[str],
    message_time: Optional[str]
) -> Optional[str]:
    """
    更可靠的下載函式 v6：
    - 區分檔案和資料夾 URL。
    - 信任 gdown 回傳的路徑。
    - 使用 shutil 壓縮資料夾。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url} (ID: {url_id})")

    try:
        downloaded_path = None

        # 判斷是檔案還是資料夾
        is_folder = "/drive/folders/" in url

        if is_folder:
            logging.info("偵測到 Google Drive 資料夾連結，將下載並壓縮。")
            # gdown.download_folder 會下載到 output_dir/資料夾名稱
            # 它會回傳下載的所有檔案路徑列表
            downloaded_files = gdown.download_folder(url, output=output_dir, quiet=False, use_cookies=True)
            if not downloaded_files:
                raise Exception("gdown.download_folder 未返回任何檔案路徑。")

            # 從第一個檔案路徑推斷出被建立的資料夾路徑
            source_dir = Path(downloaded_files[0]).parent
            zip_filename_base = Path(output_dir) / source_dir.name

            zip_path_str = shutil.make_archive(str(zip_filename_base), 'zip', str(source_dir))

            shutil.rmtree(source_dir) # 清理原始下載的資料夾
            downloaded_path = Path(zip_path_str)
        else:
            # 對於單一檔案，直接下載
            # gdown 會回傳下載後的檔案路徑
            downloaded_path_str = gdown.download(url, output=output_dir, quiet=False, fuzzy=True, use_cookies=True)
            if downloaded_path_str:
                downloaded_path = Path(downloaded_path_str)

        if not downloaded_path or not downloaded_path.exists() or downloaded_path.stat().st_size == 0:
            logging.error(f"❌ 下載失敗：gdown 未能產生有效的檔案。 URL: {url}")
            if downloaded_path and downloaded_path.exists(): downloaded_path.unlink()
            return None

        extension = downloaded_path.suffix.lower()

        # 根據我們的規則建立最終檔名
        parts = [str(url_id)]
        if author:
            sanitized_author = sanitize_for_filename(author)
            parts.append(sanitized_author)
        if message_date and message_time:
            source_timestamp_str = f"{message_date}T{message_time}:00"
            timestamp = format_iso_for_filename(source_timestamp_str)
            parts.append(timestamp)

        final_filename = f"{'_'.join(parts)}{extension}"
        final_path = Path(output_dir) / final_filename

        if final_path.exists():
            final_path.unlink()

        downloaded_path.rename(final_path)

        logging.info(f"✅ 檔案成功下載並命名為：{final_path}")
        return str(final_path)

    except gdown.exceptions.FileURLRetrievalError as e:
        logging.error(f"❌ Google Drive 檔案無法存取 (URL ID: {url_id})。請檢查權限。錯誤: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤 (URL ID: {url_id}): {e}", exc_info=True)
        return None
