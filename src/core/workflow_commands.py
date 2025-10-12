# src/core/workflow_commands.py
import logging
from typing import Dict, Any

from src.db.client import DBClient
from src.tools.universal_downloader import download_file

log = logging.getLogger(__name__)

def command_download_and_extract(db: DBClient, url: str, source_url_id: int) -> Dict[str, Any]:
    """
    工作流指令：下載一個檔案，提取其內容，並更新資料庫。

    :param db: DBClient 的實例。
    :param url: 要下載的檔案 URL。
    :param source_url_id: 該 URL 在 `extracted_urls` 表中的原始 ID。
    :return: 一個包含結果的字典，例如本地檔案路徑。
    """
    log.info(f"[指令:DOWNLOAD_AND_EXTRACT] 開始處理 URL ID: {source_url_id}, URL: {url}")

    # 更新資料庫中的狀態，表示我們開始處理這個項目
    db.update_url(source_url_id, {"status": "downloading"})

    download_dir = f"data/downloads/essay_{source_url_id}"
    success, result_path, output_type = download_file(url=url, download_dir=download_dir)

    if not success:
        log.error(f"下載項目 {source_url_id} 失敗。錯誤: {result_path}")
        db.update_url(source_url_id, {"status": "download_failed", "last_error_details": result_path})
        # 在工作流引擎中，指令失敗應該拋出異常
        raise Exception(f"檔案下載失敗: {result_path}")

    log.info(f"項目 {source_url_id} 下載成功。儲存至: {result_path}")
    db.update_url(source_url_id, {"status": "downloaded", "local_path": result_path})

    # 指令成功後，回傳一個包含重要資訊的結果字典
    # 這個結果會被序列化並儲存在 workflow_steps 表的 result 欄位中
    return {
        "local_path": result_path,
        "output_type": output_type,
        "source_url_id": source_url_id
    }

# 未來可以在此處新增更多指令函式
# def command_analyze_text(db: DBClient, local_path: str, source_url_id: int) -> Dict[str, Any]:
#     ...