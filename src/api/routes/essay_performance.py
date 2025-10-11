# src/api/routes/essay_performance.py
import httpx
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Dict, Any
import logging
import json
from pathlib import Path
import tempfile
import uuid
from datetime import datetime

# --- 專案內部模組匯入 ---
from src.core.task_manager import get_manager as get_task_manager
from src.db.client import DBClient
from src.tools.universal_downloader import download_file
from src.core.service_discovery import get_service_url as get_service_url_from_core

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/essay_performance",
    tags=["Essay Performance"],
)

# --- 微服務配置 ---
SERVICE_NAME = "essay_ingestion_service"

def get_service_url_wrapper(service_name: str) -> str:
    """
    一個包裝函式，呼叫核心服務發現模組並處理錯誤，將其轉換為適合 API 路由的 HTTPException。
    """
    url = get_service_url_from_core(service_name)
    if url is None:
        log.error(f"服務發現失敗: 無法為服務 '{service_name}' 找到 URL。")
        raise HTTPException(status_code=503, detail=f"服務 '{service_name}' 目前不可用或未註冊。")
    return url


# --- 共用 HTTP 客戶端 ---
async def get_http_client():
    async with httpx.AsyncClient() as client:
        yield client

# --- 資料模型 ---
class IngestRequest(BaseModel):
    text: str

# --- API 端點 (代理模式) ---
@router.post("/ingest_text")
async def proxy_ingest_text(
    request_body: IngestRequest,
    client: httpx.AsyncClient = Depends(get_http_client)
):
    """
    代理端點，將文字擷取請求轉發至後端的 essay_ingestion_service。
    (Jules @ 2025-10-07) 新增服務發現邏輯。
    """
    try:
        # 動態獲取微服務 URL
        service_base_url = get_service_url_wrapper(SERVICE_NAME)
        target_url = f"{service_base_url}/ingest"
        log.info(f"代理請求至動態發現的 URL: {target_url}")

        response = await client.post(
            target_url,
            json=request_body.model_dump(),
            timeout=30.0
        )

        response.raise_for_status()
        return response.json()

    except HTTPException as e:
        # 重新引發由 get_service_url 產生的 HTTPExceptions
        raise e
    except httpx.HTTPStatusError as e:
        log.error(f"微服務回傳錯誤狀態碼 {e.response.status_code}: {e.response.text}")
        try:
            detail = e.response.json()
        except json.JSONDecodeError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except httpx.RequestError as e:
        log.error(f"無法連線至小作文擷取服務 '{SERVICE_NAME}': {e}")
        raise HTTPException(
            status_code=503,
            detail="後端擷取服務目前無法使用，請稍後再試。"
        )
    except Exception as e:
        log.error(f"代理請求時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="代理請求時發生內部錯誤。")


# --- 依賴注入 ---
# 這些函式會被 FastAPI 用來提供共享的資源實例給 API 端點
# (Jules @ 2025-10-11) 修正 NameError：將 get_db_client 移至使用它的路由之前。
def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    # 這裡可以根據需要實現更複雜的生命週期管理
    # 但對於 DBClient 來說，其內部的 httpx.Client 已經管理了連線池
    return DBClient()


@router.get("/processing_items", summary="獲取所有可進行AI處理的項目")
async def get_all_processing_items(db_client: DBClient = Depends(get_db_client)):
    """
    (Jules @ 2025-10-11) 重構：獲取所有已擷取但尚未成功完成所有處理的項目。
    這確保了任何待處理、正在處理或處理失敗的項目都會顯示在清單上。
    """
    try:
        # 獲取所有已擷取的項目
        all_items = db_client.get_filtered_urls()

        # 篩選出需要顯示的項目：尚未完成 OCR 或尚未完成 AI 分析的項目
        def is_incomplete(item):
            return item.get('ocr_status') != 'completed' or item.get('ai_status') != 'completed'

        items_to_process = [item for item in all_items if is_incomplete(item)]

        # 預設按 ID 降序排序，讓最新的項目顯示在最前面
        if items_to_process:
            return sorted(items_to_process, key=lambda item: item.get('id', 0), reverse=True)
        return []
    except Exception as e:
        log.error(f"從資料庫獲取可處理項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取可處理的項目清單。")


@router.get("/items", summary="獲取所有已擷取的項目")
async def get_all_ingested_items(db_client: DBClient = Depends(get_db_client)):
    """
    從資料庫中獲取所有已透過文字擷取功能處理過的項目。
    (Jules @ 2025-10-10) 新增此端點以解決前端列表在重新載入後消失的問題。
    """
    try:
        # 使用 get_filtered_urls()，不帶任何參數以獲取所有紀錄
        all_items = db_client.get_filtered_urls()
        # 預設按 ID 降序排序，讓最新的項目顯示在最前面
        if all_items:
            return sorted(all_items, key=lambda item: item.get('id', 0), reverse=True)
        return []
    except Exception as e:
        log.error(f"從資料庫獲取小作文項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取項目清單。")


# --- 非同步下載功能 (計畫 15-4a) ---

# --- 資料模型 ---
class StartDownloadRequest(BaseModel):
    ids: List[int] = Field(..., description="要下載的項目ID列表")

class StartDownloadResponse(BaseModel):
    task_id: str = Field(..., description="用於追蹤下載進度的唯一任務ID")

# Jules: 為分析流程新增資料模型
class StartAnalysisRequest(BaseModel):
    ids: List[int] = Field(..., description="要進行分析的項目ID列表")
    all_item_ids: List[int] = Field(None, description="當前頁面上所有項目的ID列表，用於維持狀態上下文")

class StartAnalysisResponse(BaseModel):
    task_id: str = Field(..., description="用於追蹤分析進度的唯一任務ID")

# --- 背景任務邏輯 ---
def run_download_pipeline(task_id: str, item_ids: List[int], db_client: DBClient, task_manager):
    """
    在背景執行緒中運行的下載管線。
    注意：這是一個同步函式，FastAPI 會在一個獨立的執行緒池中運行它，因此不會阻塞主事件迴圈。
    """
    log.info(f"[任務 {task_id}] 背景下載管線已啟動，共 {len(item_ids)} 個項目。")

    for item_id in item_ids:
        try:
            # 1. 從資料庫查詢項目的詳細資訊和 URL
            log.info(f"[任務 {task_id}] 正在處理項目 ID: {item_id}")
            url_record = db_client.get_url_by_id(item_id)
            if not url_record or not url_record.get('url'):
                log.error(f"[任務 {task_id}] 找不到項目 ID {item_id} 的資料庫紀錄或 URL。")
                raise ValueError(f"找不到 ID {item_id} 的資料庫紀錄或 URL")

            # 2. 更新任務狀態為「下載中」，並填入從資料庫查到的詳細資訊
            details_to_update = {
                "title": url_record.get('title', '未知標題'),
                "author": url_record.get('author', '未知作者'),
                "message_date": url_record.get('message_date', '未知日期'),
                "message_time": url_record.get('message_time', '未知時間'),
            }
            task_manager.update_item_status(task_id, item_id, "DOWNLOADING", details=details_to_update)
            log.info(f"[任務 {task_id}] 項目 {item_id} 狀態更新為 DOWNLOADING。")

            # 3. 執行下載
            download_dir = f"data/downloads/essay_{item_id}"
            success, result_path, output_type = download_file(url=url_record['url'], download_dir=download_dir)

            if not success:
                log.error(f"[任務 {task_id}] 下載項目 {item_id} 失敗。錯誤: {result_path}")
                raise Exception(result_path) # 將錯誤訊息拋出以便被捕獲

            # 4. 更新資料庫和任務狀態為成功
            log.info(f"[任務 {task_id}] 項目 {item_id} 下載成功。儲存至: {result_path} ({output_type})")
            db_client.update_url(item_id, {"status": "downloaded", "local_path": result_path})
            task_manager.update_item_status(task_id, item_id, "DOWNLOADED")

        except Exception as e:
            # 5. 處理任何步驟中發生的錯誤
            error_msg = str(e)
            log.error(f"[任務 {task_id}] 處理項目 {item_id} 時發生嚴重錯誤: {error_msg}", exc_info=True)
            try:
                # 嘗試更新資料庫狀態
                db_client.update_url(item_id, {"status": "download_failed"})
            except Exception as db_e:
                log.error(f"[任務 {task_id}] 更新項目 {item_id} 狀態為 download_failed 時再次發生錯誤: {db_e}")

            task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": error_msg})

    # 標記整個大任務完成
    task_manager.complete_task(task_id)
    log.info(f"[任務 {task_id}] 所有項目處理完畢，管線結束。")


# --- 背景任務邏輯 (Jules @ 2025-10-11) 重構：合併下載與分析 ---
def run_full_analysis_pipeline(task_id: str, item_ids: List[int], db_client: DBClient, task_manager):
    """
    在背景執行緒中運行的完整處理管線，包含下載和分析兩個階段。
    """
    log.info(f"[任務 {task_id}] 完整處理管線已啟動，共 {len(item_ids)} 個項目。")

    try:
        service_base_url = get_service_url_wrapper(SERVICE_NAME)
        analysis_target_url = f"{service_base_url}/process-local-document"
        log.info(f"[任務 {task_id}] 將使用分析服務端點: {analysis_target_url}")
    except HTTPException as e:
        log.error(f"[任務 {task_id}] 無法啟動管線，因為找不到擷取服務: {e.detail}")
        for item_id in item_ids:
            task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": "後端分析服務不可用"})
        task_manager.complete_task(task_id)
        return

    with httpx.Client(timeout=600.0) as client:
        for item_id in item_ids:
            try:
                # --- 階段一：下載 ---
                task_manager.update_item_status(task_id, item_id, "DOWNLOADING")
                url_record = db_client.get_url_by_id(item_id)
                if not url_record or not url_record.get('url'):
                    raise ValueError(f"找不到 ID {item_id} 的 URL 紀錄")

                download_dir = f"data/downloads/essay_{item_id}"
                success, result_path, _ = download_file(url=url_record['url'], download_dir=download_dir)
                if not success:
                    raise Exception(f"下載失敗: {result_path}")

                db_client.update_url(item_id, {"status": "downloaded", "local_path": result_path})
                task_manager.update_item_status(task_id, item_id, "DOWNLOADED", details={"local_path": result_path})
                log.info(f"[任務 {task_id}] 項目 {item_id} 下載成功。")

                # --- 階段二：分析 ---
                task_manager.update_item_status(task_id, item_id, "PROCESSING_ANALYSIS")
                db_client.update_url(item_id, {"ocr_status": "processing", "ai_status": "processing"})

                response = client.post(analysis_target_url, json={"file_path": result_path})
                response.raise_for_status()
                analysis_result = response.json()
                log.info(f"[任務 {task_id}] 項目 {item_id} 分析成功。")

                analysis_data = analysis_result.get("analysis_data", {})
                new_title = analysis_data.get("title")
                new_author = analysis_data.get("author")

                updates_for_db = {
                    "ocr_status": "completed",
                    "ai_status": "completed",
                    "extracted_text": analysis_result.get("extracted_text"),
                    "extracted_image_paths": json.dumps(analysis_result.get("image_paths", [])),
                    "last_error_details": None
                }
                if new_title and "無法辨識" not in new_title:
                    updates_for_db["title"] = new_title
                if new_author and "無法辨識" not in new_author:
                    updates_for_db["author"] = new_author

                db_client.update_url(item_id, updates_for_db)
                task_manager.update_item_status(task_id, item_id, "COMPLETED_ANALYSIS", details=updates_for_db)

            except Exception as e:
                error_msg = str(e)
                log.error(f"[任務 {task_id}] 處理項目 {item_id} 時發生錯誤: {error_msg}", exc_info=True)
                try:
                    db_client.update_url(item_id, {"status": "failed", "ocr_status": "failed", "ai_status": "failed", "last_error_details": error_msg})
                except Exception as db_e:
                    log.error(f"[任務 {task_id}] 更新項目 {item_id} 狀態為 failed 時再次發生錯誤: {db_e}")
                task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": error_msg})

    task_manager.complete_task(task_id)
    log.info(f"[任務 {task_id}] 所有項目完整處理完畢，管線結束。")


# --- API 端點 ---
@router.post("/start_download", response_model=StartDownloadResponse, summary="啟動非同步文件下載")
async def start_download(
    request: StartDownloadRequest,
    background_tasks: BackgroundTasks,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    接收一個包含多個ID的列表，為這些ID啟動一個背景下載任務。
    - 建立一個唯一的任務ID。
    - 將下載管線 (`run_download_pipeline`) 作為背景任務加入。
    - 立即回傳任務ID，以便前端可以開始輪詢狀態。
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="ID列表不可為空。")

    log.info(f"收到 /start_download 請求，包含 {len(request.ids)} 個ID。")
    task_id = task_manager.create_task(request.ids)
    log.info(f"已為請求建立任務，Task ID: {task_id}")

    # 將耗時的下載工作新增到背景任務佇列中
    background_tasks.add_task(run_download_pipeline, task_id, request.ids, db_client, task_manager)

    return {"task_id": task_id}


@router.post("/start_full_analysis", response_model=StartAnalysisResponse, summary="啟動完整的下載與分析流程")
async def start_full_analysis(
    request: StartAnalysisRequest,
    background_tasks: BackgroundTasks,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    接收一個ID列表，為這些ID啟動一個包含下載和AI分析的完整背景任務。
    (Jules @ 2025-10-11) 新增此端點以簡化前端操作。
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="要處理的 ID 列表不可為空。")

    log.info(f"收到 /start_full_analysis 請求，包含 {len(request.ids)} 個 ID。")

    task_id = task_manager.create_task(item_ids=request.ids, context_item_ids=request.all_item_ids)
    log.info(f"已為完整分析請求建立任務，Task ID: {task_id}")

    background_tasks.add_task(run_full_analysis_pipeline, task_id, request.ids, db_client, task_manager)

    return {"task_id": task_id}


@router.get("/status/{task_id}", summary="查詢通用任務狀態")
async def get_task_status(
    task_id: str,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    根據任務ID，查詢並回傳一個任務的當前狀態。
    - 如果任務ID不存在，回傳 404 Not Found。
    - 回傳的資料包含整個任務的總體狀態以及每個子項目的詳細狀態，
      並會從資料庫補充 OCR 和 AI 分析狀態等永久性資料。
    """
    log.debug(f"收到對任務 {task_id} 的通用狀態查詢請求。")
    status = task_manager.get_task_status(task_id)
    if status is None:
        log.warning(f"查詢了不存在的任務ID: {task_id}")
        raise HTTPException(status_code=404, detail=f"找不到任務ID: {task_id}")

    # 從資料庫獲取永久性狀態並合併到回應中
    if status.get('items'):
        for item_id_str, item_data in status['items'].items():
            try:
                item_id = int(item_id_str)
                db_record = db_client.get_url_by_id(item_id)
                if db_record:
                    # 合併資料庫中的狀態
                    item_data['ocr_status'] = db_record.get('ocr_status', 'pending')
                    item_data['ai_status'] = db_record.get('ai_status', 'pending')

                    # 確保即使任務管理器中沒有，也能從資料庫填充基本資訊
                    item_data.setdefault('title', db_record.get('title', '讀取中...'))
                    item_data.setdefault('author', db_record.get('author', '未知作者'))
                    item_data.setdefault('message_date', db_record.get('message_date', ''))
                    item_data.setdefault('message_time', db_record.get('message_time', ''))
                else:
                    item_data['ocr_status'] = 'unknown'
                    item_data['ai_status'] = 'unknown'
            except (ValueError, TypeError):
                log.warning(f"處理項目 {item_id_str} 時遇到無效的 ID。")
                item_data['ocr_status'] = 'error'
                item_data['ai_status'] = 'error'

    return status


# --- Jules @ 2025-10-11: 本地分析測試端點 ---
def run_local_analysis_pipeline(task_id: str, item_id: int, db_client: DBClient, task_manager):
    """
    專為本地測試設計的背景管線，跳過下載步驟。
    """
    log.info(f"[任務 {task_id}] 本地分析管線已啟動，項目 ID: {item_id}。")
    local_file_path = None
    try:
        # --- 階段一：建立本地檔案 ---
        task_manager.update_item_status(task_id, item_id, "CREATING_LOCAL_FILE", {"message": "正在生成本地測試檔案..."})

        test_content = "這是一個本地測試檔案，用於驗證Ollama分析流程。\n台灣，美麗的寶島。"
        # 使用 tempfile 確保檔案名稱的唯一性並放置在暫存目錄
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8', dir='/tmp') as f:
            f.write(test_content)
            local_file_path = f.name

        log.info(f"[任務 {task_id}] 本地測試檔案已建立於: {local_file_path}")
        db_client.update_url(item_id, {"local_path": local_file_path, "status": "local_file_created"})
        task_manager.update_item_status(task_id, item_id, "ANALYSIS_QUEUED", {"local_path": local_file_path})

        # --- 階段二：呼叫分析服務 ---
        task_manager.update_item_status(task_id, item_id, "PROCESSING_ANALYSIS", {"message": "已傳送至分析服務"})
        db_client.update_url(item_id, {"ocr_status": "processing", "ai_status": "processing"})

        service_base_url = get_service_url_wrapper(SERVICE_NAME)
        analysis_target_url = f"{service_base_url}/process-local-document"

        with httpx.Client(timeout=600.0) as client:
            response = client.post(analysis_target_url, json={"file_path": local_file_path})
            response.raise_for_status()
            analysis_result = response.json()

        log.info(f"[任務 {task_id}] 項目 {item_id} 分析成功。")

        # --- 階段三：處理分析結果 ---
        analysis_data = analysis_result.get("analysis_data", {})
        updates_for_db = {
            "ocr_status": "completed",
            "ai_status": "completed",
            "extracted_text": analysis_result.get("extracted_text"),
            "extracted_image_paths": json.dumps(analysis_result.get("image_paths", [])),
            "last_error_details": None,
            "title": analysis_data.get("title", "本地測試標題"),
            "author": analysis_data.get("author", "本地測試作者"),
        }
        db_client.update_url(item_id, updates_for_db)
        task_manager.update_item_status(task_id, item_id, "COMPLETED_ANALYSIS", details=updates_for_db)
        log.info(f"[任務 {task_id}] 項目 {item_id} 的資料庫紀錄與任務狀態已更新。")

    except Exception as e:
        error_msg = str(e)
        log.error(f"[任務 {task_id}] 處理本地分析項目 {item_id} 時發生錯誤: {error_msg}", exc_info=True)
        try:
            db_client.update_url(item_id, {"status": "failed", "ocr_status": "failed", "ai_status": "failed", "last_error_details": error_msg})
        except Exception as db_e:
            log.error(f"[任務 {task_id}] 更新項目 {item_id} 狀態為 failed 時再次發生錯誤: {db_e}")
        task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": error_msg})
    finally:
        # 清理暫存檔案
        if local_file_path and Path(local_file_path).exists():
            try:
                Path(local_file_path).unlink()
                log.info(f"[任務 {task_id}] 已成功刪除暫存檔案: {local_file_path}")
            except OSError as e:
                log.error(f"[任務 {task_id}] 刪除暫存檔案 {local_file_path} 時失敗: {e}")

        task_manager.complete_task(task_id)
        log.info(f"[任務 {task_id}] 本地分析管線結束。")


@router.post("/local_analysis_test", response_model=StartAnalysisResponse, summary="[開發用] 觸發一個使用本地檔案的完整分析流程")
async def trigger_local_analysis_test(
    background_tasks: BackgroundTasks,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    此端點為開發和測試目的而設計，用於繞過網路下載步驟，直接測試後端的
    文件分析流程（OCR + AI）。
    """
    log.info("收到 /local_analysis_test 請求，準備啟動本地分析測試流程。")

    try:
        # 1. 創建一個虛擬的資料庫紀錄
        now = datetime.now()
        fake_url_data = {
            "url": f"local-test://{uuid.uuid4()}",
            "title": "本地分析測試",
            "author": "系統自動生成",
            "message_date": now.strftime("%Y-%m-%d"),
            "message_time": now.strftime("%H:%M"),
            "source_text": "由 /local_analysis_test 端點觸發",
            "status": "pending_local_analysis",
            "ocr_status": "pending",
            "ai_status": "pending",
        }
        inserted_id = db_client.add_new_urls(parsed_data=[fake_url_data], source_text=fake_url_data["source_text"])
        if not inserted_id or not inserted_id.get("ids"):
            raise Exception("在資料庫中創建虛擬紀錄失敗。")

        item_id = inserted_id["ids"][0]
        log.info(f"已在資料庫中創建虛擬紀錄，ID: {item_id}")

        # 2. 創建並啟動背景任務
        task_id = task_manager.create_task(item_ids=[item_id])
        log.info(f"已為本地分析請求建立任務，Task ID: {task_id}")

        background_tasks.add_task(run_local_analysis_pipeline, task_id, item_id, db_client, task_manager)

        return {"task_id": task_id}

    except Exception as e:
        log.error(f"觸發本地分析測試時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法啟動本地分析測試: {e}")