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
    更可靠的下載函式 v8 (最終版):
    - 區分檔案和資料夾 URL。
    - 直接使用 gdown 回傳的最終檔案路徑，避免 race condition。
    - 使用 shutil 壓縮資料夾。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url} (ID: {url_id})")

    # 建立一個臨時目錄來存放下載的檔案，以避免檔名衝突
    temp_output_dir = Path(output_dir) / f"temp_gdown_{uuid.uuid4()}"

    try:
        temp_output_dir.mkdir(parents=True, exist_ok=True)
        final_artifact_path = None

        is_folder = "/drive/folders/" in url

        if is_folder:
            logging.info("偵測到 Google Drive 資料夾連結，將下載並壓縮。")
            downloaded_files = gdown.download_folder(url, output=str(temp_output_dir), quiet=False, use_cookies=True)
            if not downloaded_files:
                raise Exception("gdown.download_folder 未返回任何檔案路徑。")

            # gdown 下載資料夾時，會在 output 目錄下再建立一個與資料夾同名的子目錄
            # 我們需要找到這個子目錄來壓縮
            source_dir = Path(downloaded_files[0]).parent
            zip_filename_base = temp_output_dir / source_dir.name
            zip_path_str = shutil.make_archive(str(zip_filename_base), 'zip', str(source_dir))
            final_artifact_path = Path(zip_path_str)
        else:
            # 對於單一檔案，直接下載並使用 gdown 回傳的路徑
            downloaded_path_str = gdown.download(url, output=str(temp_output_dir), quiet=False, fuzzy=True, use_cookies=True)
            if not downloaded_path_str:
                 raise Exception("gdown.download 未返回有效的檔案路徑。")
            final_artifact_path = Path(downloaded_path_str)

        if not final_artifact_path.exists() or not final_artifact_path.is_file() or final_artifact_path.stat().st_size == 0:
            raise Exception(f"下載產生的成品 {final_artifact_path} 不是一個有效的檔案。")

        extension = final_artifact_path.suffix.lower()

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

        # 將最終成品從臨時目錄移動到目標目錄
        shutil.move(str(final_artifact_path), str(final_path))

        logging.info(f"✅ 檔案成功下載並命名為：{final_path}")
        return str(final_path)

    except gdown.exceptions.FileURLRetrievalError as e:
        logging.error(f"❌ Google Drive 檔案無法存取 (URL ID: {url_id})。請檢查權限。錯誤: {e}")
        return None
    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤 (URL ID: {url_id}): {e}", exc_info=True)
        return None
    finally:
        # 無論成功或失敗，都清理臨時目錄
        if temp_output_dir.exists():
            shutil.rmtree(temp_output_dir)
