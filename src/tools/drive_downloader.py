import os
import logging
import gdown

def download_file(url: str, output_dir: str, file_name: str = None) -> str:
    """
    從指定的 URL (特別是 Google Drive) 下載檔案。
    - url: 檔案的 Google Drive 分享連結。
    - output_dir: 儲存檔案的目錄。
    - file_name: 儲存的檔案名稱。
    """
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, file_name) if file_name else output_dir
    logging.info(f"準備從 URL 下載：{url}")
    try:
        downloaded_path = gdown.download(url, output_path, quiet=False, fuzzy=True)
        if downloaded_path and os.path.exists(downloaded_path):
            logging.info(f"✅ 檔案成功下載至：{downloaded_path}")
            return downloaded_path
        else:
            logging.error("❌ 下載失敗：gdown 執行完畢但未回傳有效的檔案路徑。")
            return None
    except Exception as e:
        logging.error(f"❌ 下載過程中發生嚴重錯誤：{e}")
        return None
