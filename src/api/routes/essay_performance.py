# src/api/routes/essay_performance.py
import httpx
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List
import logging
import json
from pathlib import Path

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

# --- 依賴注入 ---
# 這些函式會被 FastAPI 用來提供共享的資源實例給 API 端點

def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    # 這裡可以根據需要實現更複雜的生命週期管理
    # 但對於 DBClient 來說，其內部的 httpx.Client 已經管理了連線池
    return DBClient()

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


# --- 背景任務邏輯 (分析) ---
# (Jules @ 2025-10-10) 重構 run_analysis_pipeline 以支援並行處理和更精確的資料庫狀態更新
async def _analyze_single_item(item_id: int, db_client: DBClient, task_manager, task_id: str, client: httpx.AsyncClient, target_url: str):
    """
    (非同步輔助函式) 處理單一項目的完整分析流程。
    """
    try:
        # 1. 從資料庫查詢項目詳情，特別是本地路徑和當前狀態
        url_record = db_client.get_url_by_id(item_id)
        if not url_record or not url_record.get('local_path'):
            raise ValueError(f"ID {item_id} 的紀錄不完整或尚未下載 (缺少 local_path)。")

        # 狀態鎖定：如果項目已在處理或已完成，則跳過
        if url_record.get('processing_status') in ['ANALYZING', 'COMPLETED']:
            log.warning(f"[任務 {task_id}] 項目 {item_id} 的狀態為 {url_record.get('processing_status')}，跳過重複分析。")
            return

        local_path = url_record['local_path']
        log.info(f"[任務 {task_id}] 開始處理項目 ID: {item_id}，檔案路徑: {local_path}")

        # 2. 立即更新資料庫和任務狀態為「分析中」
        db_client.update_url(item_id, {
            "processing_status": "ANALYZING",
            "ocr_status": "processing",
            "ai_status": "processing",
            "processing_started_at": "CURRENT_TIMESTAMP"
        })
        task_manager.update_item_status(task_id, item_id, "PROCESSING_ANALYSIS")

        # 3. 呼叫擷取服務進行分析
        response = await client.post(target_url, json={"file_path": local_path}, timeout=600.0)
        response.raise_for_status()

        # 4. 分析成功，處理回傳結果
        analysis_result = response.json()
        log.info(f"[任務 {task_id}] 項目 {item_id} 分析成功，收到分析資料。")

        analysis_data = analysis_result.get("analysis_data", {})
        new_title = analysis_data.get("title")
        new_author = analysis_data.get("author")

        updates_for_db = {
            "processing_status": "COMPLETED",
            "ocr_status": "completed",
            "ai_status": "completed",
            "extracted_text": analysis_result.get("extracted_text"),
            "extracted_image_paths": json.dumps(analysis_result.get("image_paths", [])),
            "last_error_details": None,
            "processing_completed_at": "CURRENT_TIMESTAMP"
        }

        if new_title and "無法辨識" not in new_title:
            updates_for_db["title"] = new_title
        if new_author and "無法辨識" not in new_author:
            updates_for_db["author"] = new_author

        db_client.update_url(item_id, updates_for_db)

        # 5. 更新任務管理器狀態
        details_for_task_manager = {"title": new_title, "author": new_author}
        task_manager.update_item_status(task_id, item_id, "COMPLETED_ANALYSIS", details=details_for_task_manager)

    except Exception as e:
        error_msg = str(e)
        log.error(f"[任務 {task_id}] 處理項目 {item_id} 的分析時發生錯誤: {error_msg}", exc_info=True)
        try:
            db_client.update_url(item_id, {
                "processing_status": "FAILED",
                "ocr_status": "failed",
                "ai_status": "failed",
                "last_error_details": error_msg,
                "processing_completed_at": "CURRENT_TIMESTAMP"
            })
            task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": error_msg})
        except Exception as db_err:
            log.error(f"[任務 {task_id}] 在記錄錯誤資訊至資料庫時再次發生錯誤: {db_err}")


async def run_analysis_pipeline_async(task_id: str, item_ids: List[int], db_client: DBClient, task_manager):
    """
    (非同步) 在背景執行緒中運行的分析管線，使用 asyncio.gather 實現並行處理。
    """
    log.info(f"[任務 {task_id}] 背景非同步分析管線已啟動，共 {len(item_ids)} 個項目。")
    try:
        service_base_url = get_service_url_wrapper(SERVICE_NAME)
        target_url = f"{service_base_url}/process-local-document"
        log.info(f"[任務 {task_id}] 將使用擷取服務端點: {target_url}")
    except HTTPException as e:
        log.error(f"[任務 {task_id}] 無法啟動分析管線，因為找不到擷取服務: {e.detail}")
        for item_id in item_ids:
            task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": "分析服務不可用"})
        task_manager.complete_task(task_id)
        return

    async with httpx.AsyncClient() as client:
        # 建立所有項目的非同步任務
        tasks = [
            _analyze_single_item(item_id, db_client, task_manager, task_id, client, target_url)
            for item_id in item_ids
        ]
        # 並行執行所有任務
        await asyncio.gather(*tasks)

    task_manager.complete_task(task_id)
    log.info(f"[任務 {task_id}] 所有分析項目處理完畢，非同步管線結束。")


def run_analysis_pipeline(task_id: str, item_ids: List[int], db_client: DBClient, task_manager):
    """
    用於啟動非同步分析管線的同步包裝函式。
    FastAPI 的 BackgroundTasks 需要一個同步的進入點。
    """
    import asyncio
    asyncio.run(run_analysis_pipeline_async(task_id, item_ids, db_client, task_manager))


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


# (Jules @ 2025-10-10) 新增一個輕量級端點，僅用於建立追蹤任務而不啟動任何背景工作。
class CreatePollingTaskRequest(BaseModel):
    ids: List[int] = Field(..., description="要追蹤的項目ID列表")

class CreatePollingTaskResponse(BaseModel):
    task_id: str = Field(..., description="用於追蹤狀態的唯一任務ID")

@router.post("/create_polling_task", response_model=CreatePollingTaskResponse, summary="建立僅供輪詢的任務")
async def create_polling_task(
    request: CreatePollingTaskRequest,
    task_manager = Depends(get_task_manager)
):
    """
    接收一個 ID 列表，為其建立一個任務 ID，但不觸發任何背景處理。
    此端點主要用於讓前端在處理已存在項目時，能獲取一個 task_id 來輪詢其當前狀態。
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="ID 列表不可為空。")

    log.info(f"收到 /create_polling_task 請求，為 {len(request.ids)} 個 ID 建立一個追蹤任務。")
    # 建立一個任務，但將所有 ID 都放在 context_item_ids 中，表示它們是初始狀態的一部分。
    # 真正的 "item_ids" (要處理的 ID) 留空，這樣就不會觸發任何操作。
    task_id = task_manager.create_task(item_ids=[], context_item_ids=request.ids)
    log.info(f"已為追蹤請求建立任務，Task ID: {task_id}")

    return {"task_id": task_id}


@router.post("/start_analysis", response_model=StartAnalysisResponse, summary="啟動非同步文件分析")
async def start_analysis(
    request: StartAnalysisRequest,
    background_tasks: BackgroundTasks,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    接收一個包含多個ID的列表，為這些ID啟動一個背景分析任務。
    (Jules): 增強版，現在會接收頁面上所有的 ID 以維持 UI 狀態。
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="要分析的 ID 列表不可為空。")

    log.info(f"收到 /start_analysis 請求，包含 {len(request.ids)} 個要分析的 ID，以及 {len(request.all_item_ids or [])} 個上下文 ID。")

    # (Jules): 將 all_item_ids 傳遞給任務管理器，以保留完整的 UI 上下文
    task_id = task_manager.create_task(item_ids=request.ids, context_item_ids=request.all_item_ids)
    log.info(f"已為分析請求建立任務，Task ID: {task_id}")

    # 將耗時的分析工作新增到背景任務佇列中
    background_tasks.add_task(run_analysis_pipeline, task_id, request.ids, db_client, task_manager)

    return {"task_id": task_id}


@router.get("/status/{task_id}", summary="查詢通用任務狀態")
async def get_task_status(
    task_id: str,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    根據任務ID，查詢並回傳一個任務的當前狀態。
    (Jules @ 2025-10-10) 重構：狀態的唯一真實來源是資料庫。此函式現在直接查詢資料庫。
    """
    log.debug(f"收到對任務 {task_id} 的通用狀態查詢請求。")
    task_info = task_manager.get_task_status(task_id)
    if task_info is None:
        log.warning(f"查詢了不存在的任務ID: {task_id}")
        raise HTTPException(status_code=404, detail=f"找不到任務ID: {task_id}")

    # 1. 從任務管理器獲取此任務關聯的所有 ID
    all_item_ids = task_info.get('context_item_ids', [])
    if not all_item_ids:
        log.warning(f"任務 {task_id} 中沒有找到任何關聯的項目 ID。")
        # 即使沒有ID，也回傳一個有效的空任務狀態
        return {
            "task_id": task_id,
            "status": "COMPLETED", # 如果沒有項目，可視為已完成
            "items": {}
        }

    # 2. 直接從資料庫批量查詢這些 ID 的最新狀態
    try:
        records = db_client.get_urls_by_id_list(all_item_ids)
        if not records:
            raise HTTPException(status_code=404, detail=f"在資料庫中找不到與任務 {task_id} 相關的任何項目。")
    except Exception as e:
        log.error(f"從資料庫查詢任務 {task_id} 的項目時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢資料庫時發生錯誤。")

    # 3. 建構前端所需的回應格式
    items_map = {}
    is_overall_completed = True
    for record in records:
        item_id = record['id']
        processing_status = record.get('processing_status', 'PENDING')

        # 根據 processing_status 決定前端的總體狀態
        # 注意：這裡的邏輯需要和前端的 `statusMap` 對應
        ui_status = "WAITING" # 預設值
        if processing_status == 'ANALYZING':
            ui_status = "PROCESSING_ANALYSIS"
            is_overall_completed = False
        elif processing_status == 'COMPLETED':
            ui_status = "COMPLETED_ANALYSIS"
        elif processing_status == 'FAILED':
            ui_status = "FAILED"
        elif processing_status == 'DOWNLOADED':
            ui_status = "DOWNLOADED"
        elif processing_status == 'DOWNLOADING':
            ui_status = 'DOWNLOADING'
            is_overall_completed = False

        if processing_status not in ['COMPLETED', 'FAILED']:
            is_overall_completed = False

        items_map[str(item_id)] = {
            "id": item_id,
            "status": ui_status,
            "title": record.get('title', '讀取中...'),
            "author": record.get('author', '未知作者'),
            "message_date": record.get('message_date', ''),
            "message_time": record.get('message_time', ''),
            "ocr_status": record.get('ocr_status', 'pending'),
            "ai_status": record.get('ai_status', 'pending'),
            "error_message": record.get('last_error_details')
        }

    return {
        "task_id": task_id,
        "status": "COMPLETED" if is_overall_completed else "PROCESSING",
        "items": items_map
    }