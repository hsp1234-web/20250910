# src/core/workflow_commands.py
import logging
from typing import Dict, Any

from src.db.client import DBClient
from src.tools.universal_downloader import download_file

log = logging.getLogger(__name__)

def command_download_and_extract(db: DBClient, url: str, source_url_id: int) -> Dict[str, Any]:
    """
    工作流指令：下載一個檔案，提取其內容，並更新資料庫。
    (Jules @ 2025-10-14) 已修改為可更新精細化狀態欄位。

    :param db: DBClient 的實例。
    :param url: 要下載的檔案 URL。
    :param source_url_id: 該 URL 在 `extracted_urls` 表中的原始 ID。
    :return: 一個包含結果的字典，例如本地檔案路徑。
    """
    log.info(f"[指令:DOWNLOAD_AND_EXTRACT] 開始處理 URL ID: {source_url_id}, URL: {url}")

    # 更新精細化狀態，表示我們開始處理這個項目
    db.update_url(source_url_id, {"status_download": "running", "status_extraction": "pending"})

    download_dir = f"data/downloads/essay_{source_url_id}"
    success, result_path, output_type = download_file(url=url, download_dir=download_dir)

    if not success:
        error_message = result_path # download_file 失敗時，result_path 包含錯誤訊息
        log.error(f"下載項目 {source_url_id} 失敗。錯誤: {error_message}")
        db.update_url(source_url_id, {
            "status_download": "failed",
            "status_extraction": "skipped", # 下載失敗，提取步驟跳過
            "status": "failed", # 更新總體狀態
            "last_error_details": error_message
        })
        # 在工作流引擎中，指令失敗應該拋出異常
        raise Exception(f"檔案下載失敗: {error_message}")

    log.info(f"項目 {source_url_id} 下載成功。儲存至: {result_path}")
    # 因為 download_file 合併了下載和提取，所以這裡兩者都標為成功
    db.update_url(source_url_id, {
        "status_download": "success",
        "status_extraction": "success",
        "status": "downloaded", # 更新總體狀態
        "local_path": result_path
    })

    # 指令成功後，回傳一個包含重要資訊的結果字典
    # 這個結果會被序列化並儲存在 workflow_steps 表的 result 欄位中
    return {
        "local_path": result_path,
        "output_type": output_type,
        "source_url_id": source_url_id
    }

# (Jules @ 2025-10-12) 新增分析指令
def command_analyze_text(db: DBClient, local_path: str, source_url_id: int) -> Dict[str, Any]:
    """
    工作流指令：使用 line_parser_service 分析一個本地檔案。
    (Jules @ 2025-10-14) 已修改為可更新精細化狀態欄位。
    """
    log.info(f"[指令:ANALYZE_TEXT] 開始處理檔案: {local_path} (源自 URL ID: {source_url_id})")

    # 更新精細化狀態
    db.update_url(source_url_id, {"status_ai_summary": "running"})

    try:
        # 這是一個捷徑，理想情況下應該是透過 HTTP 呼叫 line_parser_service
        # 但由於時間限制和避免循環依賴，我們暫時直接呼叫其核心邏輯
        from services.line_parser_service.document_analyzer import process_local_document
        import asyncio

        # 由於 process_local_document 是非同步的，我們需要一個事件迴圈來運行它
        analysis_result = asyncio.run(process_local_document(file_path=local_path))

        if analysis_result.get("error"):
            raise ValueError(analysis_result.get("error_details", analysis_result["error"]))

        analysis_data = analysis_result.get("analysis_data", {})
        new_title = analysis_data.get("title")
        new_author = analysis_data.get("author")

        updates_for_db = {
            "status_ai_summary": "success",
            "status": "completed", # 更新總體狀態
            "extracted_text": analysis_result.get("extracted_text"),
            "extracted_image_paths": json.dumps(analysis_result.get("image_paths", [])),
            "last_error_details": None
        }
        if new_title and "無法辨識" not in new_title:
            updates_for_db["title"] = new_title
        if new_author and "無法辨識" not in new_author:
            updates_for_db["author"] = new_author

        db.update_url(source_url_id, updates_for_db)
        log.info(f"成功分析並更新了 URL ID {source_url_id} 的資料庫紀錄。")

        return analysis_data

    except Exception as e:
        error_message = str(e)
        log.error(f"分析檔案 {local_path} 時發生錯誤: {error_message}", exc_info=True)
        db.update_url(source_url_id, {
            "status_ai_summary": "failed",
            "status": "analysis_failed", # 更新總體狀態
            "last_error_details": error_message
        })
        raise