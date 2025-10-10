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
def run_analysis_pipeline(task_id: str, item_ids: List[int], db_client: DBClient, task_manager):
    """
    在背景執行緒中運行的分析管線。
    """
    log.info(f"[任務 {task_id}] 背景分析管線已啟動，共 {len(item_ids)} 個項目。")

    try:
        # 取得 essay_ingestion_service 的 URL，如果失敗則直接中止
        service_base_url = get_service_url_wrapper(SERVICE_NAME)
        target_url = f"{service_base_url}/process-local-document"
        log.info(f"[任務 {task_id}] 將使用擷取服務端點: {target_url}")
    except HTTPException as e:
        log.error(f"[任務 {task_id}] 無法啟動分析管線，因為找不到擷取服務: {e.detail}")
        # 將所有項目的狀態都標記為失敗
        for item_id in item_ids:
            task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": "分析服務不可用"})
        task_manager.complete_task(task_id)
        return

    # 使用同步的 httpx Client，因為此函式本身就在背景執行緒中運行
    with httpx.Client(timeout=600.0) as client:
        for item_id in item_ids:
            try:
                # 1. 從資料庫查詢項目詳情，特別是本地路徑
                url_record = db_client.get_url_by_id(item_id)
                if not url_record or not url_record.get('local_path'):
                    raise ValueError(f"ID {item_id} 的紀錄不完整或尚未下載 (缺少 local_path)。")

                local_path = url_record['local_path']
                source_url = url_record['url']
                log.info(f"[任務 {task_id}] 正在處理項目 ID: {item_id}，檔案路徑: {local_path}")

                # 2. 更新資料庫和任務狀態為「處理中」
                db_client.update_url(item_id, {"ocr_status": "processing", "ai_status": "processing"})
                task_manager.update_item_status(task_id, item_id, "PROCESSING_ANALYSIS")

                # 3. 呼叫擷取服務進行分析 (Jules @ 2025-10-09: 更新 API call，只傳送 file_path)
                response = client.post(target_url, json={"file_path": local_path})
                response.raise_for_status() # 如果狀態碼不是 2xx，會拋出異常

                # 4. 分析成功，處理回傳結果並更新資料庫
                analysis_result = response.json()
                log.info(f"[任務 {task_id}] 項目 {item_id} 分析成功，收到分析資料。")

                # 從分析結果中提取核心資料
                analysis_data = analysis_result.get("analysis_data", {})

                # (Jules): 根據新需求，從 analysis_data 中提取 title 和 author
                new_title = analysis_data.get("title")
                new_author = analysis_data.get("author")

                updates_for_db = {
                    "ocr_status": "completed",
                    "ai_status": "completed",
                    "extracted_text": analysis_result.get("extracted_text"),
                    "extracted_image_paths": json.dumps(analysis_result.get("image_paths", [])),
                    "last_error_details": None # 清除舊的錯誤訊息
                }

                # (Jules): 只有在 LLM 確實回傳了有效值時才更新，避免覆蓋掉舊資料
                if new_title and "無法辨識" not in new_title:
                    updates_for_db["title"] = new_title
                if new_author and "無法辨識" not in new_author:
                    updates_for_db["author"] = new_author

                db_client.update_url(item_id, updates_for_db)

                # (Jules): 在任務管理器中也更新這些資訊，以便前端能立即看到
                details_for_task_manager = {
                    "title": new_title,
                    "author": new_author
                }
                task_manager.update_item_status(task_id, item_id, "COMPLETED_ANALYSIS", details=details_for_task_manager)

            except Exception as e:
                error_msg = str(e)
                log.error(f"[任務 {task_id}] 處理項目 {item_id} 的分析時發生錯誤: {error_msg}", exc_info=True)
                db_client.update_url(item_id, {"ocr_status": "failed", "ai_status": "failed", "last_error_details": error_msg})
                task_manager.update_item_status(task_id, item_id, "FAILED", details={"error_message": error_msg})

    task_manager.complete_task(task_id)
    log.info(f"[任務 {task_id}] 所有分析項目處理完畢，管線結束。")


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


@router.post("/start_analysis", response_model=StartAnalysisResponse, summary="啟動非同步文件分析")
async def start_analysis(
    request: StartAnalysisRequest,
    background_tasks: BackgroundTasks,
    db_client: DBClient = Depends(get_db_client),
    task_manager = Depends(get_task_manager)
):
    """
    接收一個包含多個ID的列表，為這些ID啟動一個背景分析任務。
    """
    if not request.ids:
        raise HTTPException(status_code=400, detail="ID列表不可為空。")

    log.info(f"收到 /start_analysis 請求，包含 {len(request.ids)} 個ID。")
    task_id = task_manager.create_task(request.ids)
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