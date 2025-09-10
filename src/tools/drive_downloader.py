import os
import logging
import gdown
from datetime import datetime
from pathlib import Path
import pytz

def download_file(url: str, output_dir: str, file_name: str = None) -> str | None:
    """
    從指定的 URL (特別是 Google Drive) 智慧地檔案。
    - 會讓 gdown 自動偵測原始檔名與副檔名。
    - 會將檔案重新命名為包含台北時區 ISO 時間戳的格式。
    - url: 檔案的 Google Drive 分享連結。
    - output_dir: 儲存檔案的目錄。
    - file_name: (已棄用) 此參數不再使用，檔名會自動生成。
    """
    os.makedirs(output_dir, exist_ok=True)
    logging.info(f"準備從 URL 下載：{url}")

    try:
        # 讓 gdown 自動偵測檔名並下載到指定目錄。傳入 output_dir 而不是完整路徑。
        downloaded_path_str = gdown.download(url, output_dir, quiet=False, fuzzy=True)

        if not downloaded_path_str or not os.path.exists(downloaded_path_str):
            logging.error("❌ 下載失敗：gdown 執行完畢但未回傳有效的檔案路徑。")
            return None

        downloaded_path = Path(downloaded_path_str)

        # --- 統一時間戳命名 ---
        # gdown 應該已經儲存了帶有正確副檔名的檔案
        try:
            # 使用 pytz 來處理時區
            tz_taipei = pytz.timezone('Asia/Taipei')
            timestamp = datetime.now(tz_taipei).strftime('%Y-%m-%dT%H-%M-%S')
        except Exception as e:
            # 如果 pytz 有問題，提供一個不含時區的備案
            logging.warning(f"無法載入台北時區，將使用 UTC 時間戳: {e}")
            timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H-%M-%S')

        # 組合新檔名，保留原始檔名和副檔名
        new_filename = f"{timestamp}_{downloaded_path.name}"
        final_path = downloaded_path.with_name(new_filename)

        # 重新命名
        downloaded_path.rename(final_path)

        logging.info(f"✅ 檔案成功下載並重新命名為：{final_path}")
        return str(final_path)

    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤：{e}", exc_info=True)
        return None
