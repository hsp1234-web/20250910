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
    更可靠的下載函式 v7 (最終版):
    - 為每次下載建立一個唯一的臨時子目錄，以隔離檔案。
    - 信任 gdown 函式庫來處理下載。
    - 如果下載的是資料夾，使用 shutil 將其壓縮。
    - 最後根據系統規則重新命名檔案。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url} (ID: {url_id})")

    # 建立一個臨時的、唯一的子目錄來進行下載，避免檔案衝突
    temp_target_dir = Path(output_dir) / f"temp_download_{uuid.uuid4()}"

    try:
        temp_target_dir.mkdir()

        # 將所有內容下載到這個臨時目錄中
        # gdown.download 會回傳下載的檔案路徑，gdown.download_folder 會回傳一個路徑列表
        is_folder = "/drive/folders/" in url
        if is_folder:
            downloaded_items = gdown.download_folder(url, output=str(temp_target_dir), quiet=False, use_cookies=True)
        else:
            downloaded_items = [gdown.download(url, output=str(temp_target_dir), quiet=False, fuzzy=True, use_cookies=True)]

        if not downloaded_items or downloaded_items[0] is None:
            raise Exception("gdown 未返回有效的檔案路徑。")

        # 找出下載的成品 (可能是檔案或資料夾)
        # gdown 下載資料夾時，會在 output 目錄下再建立一個以資料夾命名的子目錄
        items_in_temp_dir = list(temp_target_dir.iterdir())
        if not items_in_temp_dir:
            raise Exception("臨時下載目錄中找不到任何檔案。")

        # 假設下載的成品是臨時目錄中的第一個項目
        downloaded_artifact = items_in_temp_dir[0]

        # 如果成品是資料夾，壓縮它
        if downloaded_artifact.is_dir():
            logging.info(f"偵測到下載的是資料夾，路徑: {downloaded_artifact}。將其壓縮為 .zip。")
            zip_filename_base = str(Path(output_dir) / downloaded_artifact.name)
            zip_path_str = shutil.make_archive(zip_filename_base, 'zip', str(downloaded_artifact))

            final_artifact_path = Path(zip_path_str)
        else:
            final_artifact_path = downloaded_artifact

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

        final_artifact_path.rename(final_path)

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
        if temp_target_dir.exists():
            shutil.rmtree(temp_target_dir)
