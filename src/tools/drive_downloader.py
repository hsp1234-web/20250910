import os
import logging
import gdown
from datetime import datetime
from pathlib import Path
import magic  # 新增 magic 函式庫
import mimetypes  # 用於從 MIME 類型獲取副檔名

# 建立一個 MIME 類型到副檔名的擴充對照表
# mimetypes 有時候無法處理一些常見的 Office 文件格式
MIME_EXTENSION_MAP = {
    'application/pdf': '.pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
    'application/msword': '.doc',
    'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
    'application/vnd.ms-powerpoint': '.ppt',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
    'application/vnd.ms-excel': '.xls',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'image/gif': '.gif',
    'text/plain': '.txt',
}

def get_extension_from_mime(mime_type: str) -> str:
    """根據 MIME 類型獲取檔案副檔名。"""
    if mime_type in MIME_EXTENSION_MAP:
        return MIME_EXTENSION_MAP[mime_type]
    # 如果不在自訂的 map 中，嘗試使用標準函式庫
    ext = mimetypes.guess_extension(mime_type)
    return ext if ext else ''  # 如果找不到則返回空字串

# 修改函式簽名以接收 url_id 和 created_at
def download_file(url: str, output_dir: str, url_id: int, created_at: str) -> str | None:
    """
    從指定的 URL 智慧地檔案，並使用提供的中繼資料來進行命名。
    - 使用 python-magic 強制偵測檔案類型以保證副檔名正確。
    - 使用資料庫 ID 和建立時間來產生統一、穩定的檔名。

    Args:
        url: 檔案的 Google Drive 分享連結。
        output_dir: 儲存檔案的目錄。
        url_id: 資料庫中的 URL ID，用於命名。
        created_at: URL 在資料庫中建立的時間戳 (字串格式)，用於命名。

    Returns:
        成功下載後檔案的最終路徑，或在失敗時返回 None。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載 (ID: {url_id})：{url}")

    try:
        # 讓 gdown 自動偵測檔名並下載。gdown 會回傳它儲存檔案的路徑。
        # 我們不再關心 gdown 產生的檔名，只關心下載的內容本身。
        downloaded_path_str = gdown.download(url, output_dir, quiet=False, fuzzy=True)

        if not downloaded_path_str or not os.path.exists(downloaded_path_str):
            logging.error(f"❌ 下載失敗 (ID: {url_id})：gdown 未回傳有效的檔案路徑。")
            return None

        downloaded_path = Path(downloaded_path_str)

        # --- 核心檔名修復邏輯 ---

        # 1. 使用 python-magic 偵測副檔名
        try:
            mime_type = magic.from_file(str(downloaded_path), mime=True)
            extension = get_extension_from_mime(mime_type)
            if not extension:
                # 如果偵測失敗，至少給一個 .bin 作為備案，避免無副檔名的情況
                logging.warning(f"無法從 MIME 類型 '{mime_type}' 偵測到副檔名，使用 .bin 作為備案。")
                extension = '.bin'
            logging.info(f"偵測到檔案 (ID: {url_id}) 的 MIME 類型為 '{mime_type}'，對應副檔名 '{extension}'。")
        except Exception as e:
            logging.error(f"❌ 使用 python-magic 偵測檔案類型時發生錯誤 (ID: {url_id})：{e}", exc_info=True)
            # 即使偵測失敗，也要嘗試清理已下載的暫存檔
            downloaded_path.unlink()
            return None

        # 2. 格式化時間戳
        try:
            # created_at 來自資料庫，格式通常是 'YYYY-MM-DD HH:MM:SS'
            # 我們需要先將其解析為 datetime 物件
            dt_object = datetime.fromisoformat(created_at)
            # 然後再格式化為我們需要的檔名格式
            timestamp = dt_object.strftime('%Y-%m-%dT%H-%M-%S')
        except ValueError:
            logging.warning(f"無法解析時間戳 '{created_at}'，將使用當前 UTC 時間作為備案。")
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')

        # 3. 組合新檔名
        base_filename = f"file_{url_id}"
        new_filename = f"{timestamp}_{base_filename}{extension}"
        final_path = downloaded_path.with_name(new_filename)

        # 4. 重新命名
        downloaded_path.rename(final_path)

        logging.info(f"✅ 檔案 (ID: {url_id}) 成功下載並重新命名為：{final_path}")
        return str(final_path)

    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤 (ID: {url_id})：{e}", exc_info=True)
        # 如果下載過程中 gdown 本身就拋出例外，可能沒有 downloaded_path_str
        # 但如果有，我們應該嘗試刪除不完整的下載檔案
        if 'downloaded_path' in locals() and downloaded_path.exists():
            try:
                downloaded_path.unlink()
                logging.info(f"已清理不完整的下載檔案：{downloaded_path}")
            except OSError as unlink_error:
                logging.error(f"清理不完整檔案 {downloaded_path} 時失敗: {unlink_error}")
        return None
