# api_server.py
import uuid
import shutil
import logging
import json
import subprocess
import sys
import threading
import re
import asyncio
import os
import time
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import Optional, Dict, List
from contextlib import asynccontextmanager
from urllib.parse import unquote, quote
from pydantic import BaseModel
import psutil

# --- 修正模組匯入路徑 ---
# 將專案的 src 目錄新增到 Python 的搜尋路徑中，
# 這樣才能正確找到 db.client 等模組。
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.client import get_client

# --- JULES 於 2025-08-09 的修改：設定應用程式全域時區 ---
# 為了確保所有日誌和資料庫時間戳都使用一致的時區，我們在應用程式啟動的
# 最早期階段就將時區環境變數設定為 'Asia/Taipei'。
os.environ['TZ'] = 'Asia/Taipei'
if sys.platform != 'win32':
    time.tzset()
# --- 時區設定結束 ---

# --- 模式設定 ---
# JULES: 改為透過環境變數來決定模擬模式，以便與 Circus 整合
# 預設為非模擬模式 (真實模式)
IS_MOCK_MODE = os.environ.get("API_MODE", "real") == "mock"

# --- 路徑設定 ---
# 以此檔案為基準，定義專案根目錄
# 因為此檔案現在位於 src/api/ 中，所以根目錄是其上上層目錄
ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# --- 主日誌設定 ---
# 主日誌器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # 輸出到控制台
)
log = logging.getLogger('api_server')

def setup_database_logging():
    """設定資料庫日誌處理器。"""
    try:
        from db.log_handler import DatabaseLogHandler
        root_logger = logging.getLogger()
        # 檢查是否已經有同類型的 handler，避免重複加入
        if not any(isinstance(h, DatabaseLogHandler) for h in root_logger.handlers):
            root_logger.addHandler(DatabaseLogHandler(source='api_server'))
            log.info("資料庫日誌處理器設定完成 (source: api_server)。")
    except Exception as e:
        log.error(f"整合資料庫日誌時發生錯誤: {e}", exc_info=True)


# Frontend action logging is now handled by the centralized database logger.


# --- WebSocket 連線管理器 ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        log.info(f"新用戶端連線。目前共 {len(self.active_connections)} 個連線。")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        log.info(f"一個用戶端離線。目前共 {len(self.active_connections)} 個連線。")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

    async def broadcast_json(self, data: dict):
        for connection in self.active_connections:
            await connection.send_json(data)

manager = ConnectionManager()


# --- DB 客戶端 ---
# 在模組加載時獲取客戶端單例
# 客戶端內部有重試機制，會等待 DB 管理者服務就緒
db_client = get_client()

# --- FastAPI Lifespan Manager ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在應用程式啟動時執行的程式碼
    setup_database_logging()
    log.info("資料庫日誌處理器已透過 lifespan 事件設定。")
    yield
    # 可以在此處加入應用程式關閉時執行的程式碼

# --- FastAPI 應用實例 ---
app = FastAPI(title="鳳凰音訊轉錄儀 API (v3 - 重構)", version="3.0", lifespan=lifespan)

# --- 中介軟體 (Middleware) ---
# JULES: 新增 CORS 中介軟體以允許來自瀏覽器腳本的跨來源請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源
    allow_credentials=True,
    allow_methods=["*"],  # 允許所有方法
    allow_headers=["*"],  # 允許所有標頭
)

# --- 整合模組化路由 ---
from api.routes import ui, page1_ingestion, page2_downloader, page3_processor, page4_analyzer, page5_backup

# UI 路由 (提供 HTML 頁面)
app.include_router(ui.router, tags=["UI"])

# API 路由 (提供資料介面)
app.include_router(page1_ingestion.router, prefix="/api/ingestion", tags=["API: 網址提取"])
app.include_router(page2_downloader.router, prefix="/api/downloader", tags=["API: 批次下載"])
app.include_router(page3_processor.router, prefix="/api/processor", tags=["API: 檔案處理"])
app.include_router(page4_analyzer.router, prefix="/api/analyzer", tags=["API: AI 分析與提示詞"])
app.include_router(page5_backup.router, prefix="/api/backup", tags=["API: 備份管理"])

# --- 路徑設定 ---
# 新的上傳檔案儲存目錄
UPLOADS_DIR = ROOT_DIR / "uploads"
REPORTS_DIR = ROOT_DIR / "reports"
# 靜態檔案目錄
STATIC_DIR = ROOT_DIR / "src" / "static"

# 確保目錄存在
UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)
if not STATIC_DIR.exists():
    log.warning(f"靜態檔案目錄 {STATIC_DIR} 不存在，前端頁面可能無法載入。")
else:
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
    # JULES'S FIX (2025-08-13): 移除有問題的 StaticFiles 掛載，改用自訂端點

# JULES'S FIX (2025-08-13): 根據計畫，新增此端點來處理複雜檔名
@app.get("/media/{file_path:path}")
async def serve_media_files(file_path: str):
    """
    一個新的API端點，專門用來安全地提供媒體檔案。
    它會手動處理URL解碼，以解決複雜檔名的問題。
    """
    try:
        # URL 解碼，將 %20 轉為空格，處理中文等
        decoded_path = unquote(file_path)
        # 建立一個安全的路徑，避免路徑遍歷攻擊
        safe_path = os.path.normpath(os.path.join(UPLOADS_DIR, decoded_path))

        # 再次確認路徑是在 UPLOADS_DIR 下
        if not safe_path.startswith(str(UPLOADS_DIR)):
             raise HTTPException(status_code=403, detail="禁止存取。")

        if os.path.exists(safe_path) and os.path.isfile(safe_path):
            return FileResponse(safe_path)
        else:
            log.warning(f"請求的媒體檔案不存在: {safe_path}")
            return JSONResponse(status_code=404, content={"detail": "File not found"})
    except Exception as e:
        log.error(f"服務媒體檔案時發生錯誤: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})


def convert_to_media_url(absolute_path_str: str) -> str:
    """將絕對檔案系統路徑轉換為可公開存取的 /media URL。"""
    try:
        absolute_path = Path(absolute_path_str)
        # 尋找相對於 UPLOADS_DIR 的路徑
        relative_path = absolute_path.relative_to(UPLOADS_DIR)
        # 將路徑的每個部分都進行 URL 編碼，以處理特殊字元
        # safe='' 參數確保連 '/' 也會被編碼，如果有的話
        encoded_path = '/'.join(quote(part, safe='') for part in relative_path.parts)

        # JULES DEBUG (2025-08-31): 根據最新分析報告，此處是造成媒體預覽失敗的關鍵。
        # 舊的寫法 `relative_path.as_posix()` 沒有對檔名中的 '#' 或空格等特殊字元進行編碼，
        # 導致瀏覽器無法正確請求 URL。新的寫法使用 `urllib.parse.quote` 進行了修正。
        # 注意：我們只對路徑的「部分」進行編碼，而不是整個 URL，以保留斜線分隔符。

        # 使用 quote 取代 as_posix() 來確保 URL 安全
        return f"/media/{encoded_path}"
    except (ValueError, TypeError):
        log.warning(f"無法將路徑 {absolute_path_str} 轉換為媒體 URL。回傳原始路徑。")
        return absolute_path_str


# --- API 端點 ---

@app.get("/", response_class=HTMLResponse)
async def serve_main_page(request: Request):
    """根端點，提供專案的中心主頁 (main.html)。"""
    html_file_path = STATIC_DIR / "main.html"
    if not html_file_path.is_file():
        log.error(f"找不到主頁檔案: {html_file_path}")
        raise HTTPException(status_code=404, detail="找不到主頁檔案 (main.html)")
    return HTMLResponse(content=html_file_path.read_text(encoding="utf-8"), status_code=200)


def check_model_exists(model_size: str) -> bool:
    """
    檢查指定的 Whisper 模型是否已經被下載到本地快取。
    """
    # JULES'S FIX: 增加一個環境變數來強制使用模擬轉錄器，以支援混合模式測試
    force_mock = os.environ.get("FORCE_MOCK_TRANSCRIBER") == "true"
    tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE or force_mock else "transcriber.py")
    log.info(f"使用 '{tool_script_path}' 檢查模型 '{model_size}' 是否存在...")

    # 我們透過呼叫一個輕量級的工具腳本來檢查。
    check_command = [sys.executable, str(tool_script_path), "--command=check", f"--model_size={model_size}"]
    try:
        # 在模擬模式下，mock_transcriber.py 會永遠回傳 "exists"
        result = subprocess.run(check_command, capture_output=True, text=True, check=True)
        output = result.stdout.strip().lower()
        log.info(f"模型 '{model_size}' 檢查結果: {output}")
        # 必須完全匹配 "exists"，避免 "not_exists" 被錯誤判斷為 True
        return output == "exists"
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.error(f"檢查模型 '{model_size}' 時發生錯誤: {e}")
        return False

@app.post("/api/transcribe", status_code=202)
async def create_transcription_task(
    file: UploadFile = File(...),
    model_size: str = Form("tiny"),
    language: Optional[str] = Form(None),
    beam_size: int = Form(5)
):
    """
    接收音訊檔案，根據模型是否存在，決定是直接建立轉錄任務，
    還是先建立一個下載任務和一個依賴於它的轉錄任務。
    """
    # 1. 檢查模型是否存在
    model_is_present = check_model_exists(model_size)

    # 2. 保存上傳的檔案
    transcribe_task_id = str(uuid.uuid4())
    file_extension = Path(file.filename).suffix or ".wav"
    saved_file_path = UPLOADS_DIR / f"{transcribe_task_id}{file_extension}"
    try:
        with open(saved_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"檔案已儲存至: {saved_file_path}")
    except Exception as e:
        log.error(f"❌ 儲存檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法儲存上傳的檔案: {e}")
    finally:
        await file.close()

    # 3. 根據模型是否存在來建立任務
    transcription_payload = {
        "input_file": str(saved_file_path),
        "original_filename": file.filename, # JULES'S FIX: Store the original filename
        "output_dir": "transcripts",
        "model_size": model_size,
        "language": language,
        "beam_size": beam_size
    }

    if model_is_present:
        # 模型已存在，直接建立轉錄任務
        log.info(f"✅ 模型 '{model_size}' 已存在，直接建立轉錄任務: {transcribe_task_id}")
        db_client.add_task(transcribe_task_id, json.dumps(transcription_payload), task_type='transcribe')
        # JULES: 修正 API 回應，使其與前端的通用處理邏輯一致，補上 type 欄位
        return {"task_id": transcribe_task_id, "type": "transcribe"}
    else:
        # 模型不存在，建立下載任務和依賴的轉錄任務
        download_task_id = str(uuid.uuid4())
        log.warning(f"⚠️ 模型 '{model_size}' 不存在。建立下載任務 '{download_task_id}' 和依賴的轉錄任務 '{transcribe_task_id}'")

        download_payload = {"model_size": model_size}
        db_client.add_task(download_task_id, json.dumps(download_payload), task_type='download')

        db_client.add_task(transcribe_task_id, json.dumps(transcription_payload), task_type='transcribe', depends_on=download_task_id)

        # 我們回傳轉錄任務的 ID，讓前端可以追蹤最終結果
        return JSONResponse(content={"tasks": [
            {"task_id": download_task_id, "type": "download"},
            {"task_id": transcribe_task_id, "type": "transcribe"}
        ]})


@app.get("/api/status/{task_id}")
async def get_task_status_endpoint(task_id: str):
    """
    根據任務 ID，從資料庫查詢任務狀態。
    """
    log.debug(f"🔍 正在查詢任務狀態: {task_id}")
    status_info = db_client.get_task_status(task_id)

    if not status_info:
        log.warning(f"❓ 找不到任務 ID: {task_id}")
        raise HTTPException(status_code=404, detail="找不到指定的任務 ID")

    # DBClient 回傳的已經是 dict，無需轉換
    response_data = status_info

    # 嘗試解析 JSON 結果
    if response_data.get("result"):
        try:
            response_data["result"] = json.loads(response_data["result"])
        except json.JSONDecodeError:
            # 如果不是合法的 JSON，就以原始字串形式回傳
            log.warning(f"任務 {task_id} 的結果不是有效的 JSON 格式。")
            pass

    log.info(f"✅ 回傳任務 {task_id} 的狀態: {response_data['status']}")
    return JSONResponse(content=response_data)


@app.post("/api/log/action", status_code=200)
async def log_action_endpoint(payload: Dict):
    """
    接收前端發送的操作日誌，並透過資料庫日誌處理器記錄。
    """
    action = payload.get("action", "unknown_action")
    # 獲取一個專門的 logger 來標識這些日誌的來源為 'frontend_action'
    # DatabaseLogHandler 會擷取這個日誌，並將其與 logger 名稱一起存入資料庫
    action_logger = logging.getLogger('frontend_action')
    action_logger.info(action)

    log.info(f"📝 已將前端操作記錄到資料庫: {action}") # 同時在主控台也顯示日誌
    return {"status": "logged"}


@app.get("/api/application_status")
async def get_application_status():
    """
    獲取核心應用的狀態，例如模型是否已載入。
    """
    # TODO: 這部分將在後續與 worker 狀態同步
    return {
        "model_loaded": False,
        "active_model": None,
        "message": "等待使用者操作"
    }

@app.get("/api/system/readiness")
async def system_readiness_check():
    """
    檢查核心依賴（如 yt-dlp）是否已準備就緒。
    """
    # 使用 shutil.which 檢查 yt-dlp 是否在系統 PATH 中且可執行
    yt_dlp_path = shutil.which("yt-dlp")
    is_ready = yt_dlp_path is not None

    if is_ready:
        log.info(f"✅ 系統就緒檢查：成功找到 yt-dlp 於 {yt_dlp_path}")
        return {"ready": True}
    else:
        log.warning("⚠️ 系統就緒檢查：找不到 yt-dlp。前端功能可能受限。")
        return {"ready": False}

@app.get("/api/system_stats")
async def get_system_stats():
    """
    獲取並回傳當前的系統資源使用狀態（CPU, RAM, GPU）。
    """
    # CPU
    cpu_usage = psutil.cpu_percent(interval=0.1)

    # RAM
    ram = psutil.virtual_memory()
    ram_usage = ram.percent

    # GPU (透過 nvidia-smi)
    gpu_usage = None
    gpu_detected = False
    try:
        # 執行 nvidia-smi 命令
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, check=True
        )
        # 解析輸出
        gpu_usage = float(result.stdout.strip())
        gpu_detected = True
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        # nvidia-smi 不存在或執行失敗
        log.debug(f"無法獲取 GPU 資訊: {e}")
        gpu_usage = None
        gpu_detected = False

    return {
        "cpu_usage": cpu_usage,
        "ram_usage": ram_usage,
        "gpu_usage": gpu_usage,
        "gpu_detected": gpu_detected,
    }


@app.get("/api/tasks")
async def get_all_tasks_endpoint():
    """
    獲取所有任務的列表，用於前端展示。
    """
    tasks = db_client.get_all_tasks()
    # 嘗試解析 payload 和 result 中的 JSON 字串
    for task in tasks:
        try:
            if task.get("payload"):
                task["payload"] = json.loads(task["payload"])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"任務 {task.get('task_id')} 的 payload 不是有效的 JSON。")
            pass # 保持原樣
        try:
            if task.get("result"):
                task["result"] = json.loads(task["result"])
        except (json.JSONDecodeError, TypeError):
            log.warning(f"任務 {task.get('task_id')} 的 result 不是有效的 JSON。")
            pass # 保持原樣
    return JSONResponse(content=tasks)


@app.get("/api/logs")
async def get_system_logs_endpoint(
    levels: List[str] = Query(None, alias="level"),
    sources: List[str] = Query(None, alias="source")
):
    """
    獲取系統日誌，可按等級和來源進行篩選。
    """
    log.info(f"API: 正在查詢系統日誌 (Levels: {levels}, Sources: {sources})")
    try:
        logs = db_client.get_system_logs(levels=levels, sources=sources)
        return JSONResponse(content=logs)
    except Exception as e:
        log.error(f"❌ 查詢系統日誌時 API 出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢系統日誌時發生內部錯誤")


@app.get("/api/download/{task_id}")
async def download_transcript(task_id: str):
    """
    根據任務 ID 下載轉錄結果檔案。
    """
    task = db_client.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="找不到指定的任務 ID。")

    if task['status'] != '已完成':
        raise HTTPException(status_code=400, detail="任務尚未完成，無法下載。")

    try:
        # 從 result 欄位解析出檔名
        result_data = json.loads(task['result'])
        # 依序檢查可能的路徑鍵名，以支援所有任務類型
        output_filename = (
            result_data.get("transcript_path") or
            result_data.get("output_path") or
            result_data.get("html_report_path") or
            result_data.get("pdf_report_path")
        )

        if not output_filename:
            raise HTTPException(status_code=500, detail="任務結果中未包含有效的檔案路徑。")

        # JULES'S FIX 2025-08-14: 將 URL 路徑轉換回檔案系統絕對路徑
        # 資料庫中儲存的是像 /media/reports/report.html 這樣的 URL，
        # 我們需要將其轉換回像 /app/uploads/reports/report.html 這樣的絕對檔案系統路徑。
        if output_filename.startswith('/media/'):
            # 移除 '/media/' 前綴並與上傳目錄合併
            relative_path = output_filename.lstrip('/media/')
            # JULES'S FIX 2025-08-31: 新增 URL 解碼步驟
            # 這是解決「檔案名稱過長」錯誤的關鍵。從資料庫取出的路徑是
            # URL 編碼過的 (例如 'file%20name.txt')，我們必須將其解碼回
            # 'file name.txt' 才能讓檔案系統找到它。
            decoded_relative_path = unquote(relative_path)
            file_path = UPLOADS_DIR / decoded_relative_path
        else:
            # 作為備用，如果路徑不是 /media/ 開頭，則假設它是一個絕對路徑
            # 這可以保持對舊資料格式的相容性
            file_path = Path(output_filename)

        if not file_path.is_file():
            log.error(f"❌ 檔案系統中的檔案不存在: {file_path}")
            raise HTTPException(status_code=404, detail="檔案遺失或無法讀取。")

        # 提供檔案下載
        ext = file_path.suffix.lower()
        if ext == '.pdf':
            media_type = 'application/pdf'
        elif ext == '.html':
            media_type = 'text/html'
        elif ext == '.mp4':
            media_type = 'video/mp4'
        elif ext in ['.mp3', '.m4a', '.wav', '.flac']:
            media_type = f'audio/{ext.strip(".")}'
        else:
            media_type = 'text/plain'
        return FileResponse(path=file_path, filename=file_path.name, media_type=media_type)

    except (json.JSONDecodeError, KeyError) as e:
        log.error(f"❌ 解析任務 {task_id} 的結果時出錯: {e}")
        raise HTTPException(status_code=500, detail="無法解析任務結果。")


@app.post("/api/rename/{task_id}", status_code=200)
async def rename_task_file(task_id: str, request: Request):
    """
    重新命名與已完成任務關聯的檔案。
    """
    log.info(f"收到重新命名任務 {task_id} 的請求。")
    try:
        data = await request.json()
        new_filename_base = data.get("new_filename")
        if not new_filename_base:
            raise HTTPException(status_code=400, detail="請求中未提供 'new_filename'。")

        task = db_client.get_task_status(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="找不到指定的任務 ID。")
        if task['status'] != '已完成':
            raise HTTPException(status_code=400, detail="只能重新命名已完成的任務。")

        result_data = json.loads(task['result'])
        old_path_str = result_data.get("output_path")
        if not old_path_str:
            raise HTTPException(status_code=500, detail="任務結果中找不到檔案路徑。")

        # JULES DEBUG (2025-08-31): 根據最新分析報告，此處是造成重新命名失敗的關鍵。
        # old_path_str 是一個 URL 路徑 (例如 /media/file.mp4)，而不是檔案系統路徑。
        # 我們需要將其轉換回絕對檔案系統路徑 (例如 /app/uploads/file.mp4)。
        if old_path_str.startswith('/media/'):
            # 移除 '/media/' 前綴並與上傳目錄合併
            relative_path = old_path_str.lstrip('/media/')
            # 這裡需要對 relative_path 進行 URL 解碼，以處理檔名中的 %20 等字元
            decoded_relative_path = unquote(relative_path)
            old_path = UPLOADS_DIR / decoded_relative_path
        else:
            # 作為備用，如果路徑不是 /media/ 開頭，則假設它是一個絕對路徑
            old_path = Path(old_path_str)

        file_extension = old_path.suffix
        new_path = old_path.with_name(f"{new_filename_base}{file_extension}")

        if old_path == new_path:
            return {"status": "success", "message": "新舊檔名相同，無需變更。", "new_filename": new_filename_base}

        if new_path.exists():
            raise HTTPException(status_code=409, detail=f"目標檔名 {new_path.name} 已存在。")

        os.rename(old_path, new_path)
        log.info(f"檔案已從 {old_path} 重新命名為 {new_path}")

        # 更新資料庫中的結果
        # JULES DEBUG (2025-08-31): 重新命名後，我們需要將新的「檔案系統路徑」轉換回「媒體 URL」，
        # 然後再存入資料庫，以保持資料格式的一致性。
        result_data["output_path"] = convert_to_media_url(str(new_path))
        result_data["video_title"] = new_filename_base

        db_client.update_task_status(task_id, '已完成', json.dumps(result_data))
        log.info(f"已更新資料庫中任務 {task_id} 的結果。")

        return {"status": "success", "message": "檔案重新命名成功。", "new_filename": new_filename_base}

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="無法解析任務結果。")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="找不到要重新命名的原始檔案。")
    except Exception as e:
        log.error(f"❌ 重新命名檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")




@app.post("/api/upload_cookies", status_code=200)
async def upload_cookies_file(file: UploadFile = File(...)):
    """
    接收使用者上傳的 cookies.txt 檔案並儲存。
    """
    if "cookies.txt" not in file.filename.lower():
        raise HTTPException(status_code=400, detail="檔案名稱必須是 'cookies.txt' 或包含該字樣。")

    cookies_path = UPLOADS_DIR / "cookies.txt"
    try:
        with open(cookies_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        log.info(f"🍪 Cookies 檔案已儲存至: {cookies_path}")
        return {"status": "success", "message": "Cookies 檔案上傳成功。"}
    except Exception as e:
        log.error(f"❌ 儲存 Cookies 檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"無法儲存 Cookies 檔案: {e}")
    finally:
        await file.close()


# --- YouTube 功能相關 API ---

@app.post("/api/youtube/validate_api_key")
async def validate_api_key(request: Request):
    """接收前端傳來的 API Key 並進行驗證。"""
    try:
        payload = await request.json()
        api_key = payload.get("api_key")
        if not api_key:
            raise HTTPException(status_code=400, detail="未提供 API 金鑰。")

        if IS_MOCK_MODE:
            log.info("模擬模式：將非空 API 金鑰視為有效。")
            return {"valid": True}

        tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
        cmd = [sys.executable, str(tool_script_path), "--command=validate_key"]

        # JULES'S FIX V3: 建立一個最小化的乾淨環境來執行驗證。
        # 這是為了防止 Google 的函式庫自動從沙箱環境中繼承任何「應用程式預設憑證」，
        # 從而確保驗證過程只使用使用者提供的 API 金鑰。
        minimal_env = {
            "PATH": os.environ.get("PATH", ""),
            "GOOGLE_API_KEY": api_key,
            # 在某些系統上，特別是 Windows，需要 SYSTEMROOT。為保險起見加入。
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")
        }

        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', env=minimal_env, check=False)

        if result.returncode == 0:
            log.info(f"API 金鑰驗證成功。")
            return {"valid": True}
        else:
            log.warning(f"API 金鑰驗證失敗。Stderr: {result.stderr.strip()}")
            error_message = result.stderr.strip()
            detail = error_message if error_message else "金鑰驗證失敗，請檢查主控台日誌以了解詳情。"
            return JSONResponse(status_code=400, content={"valid": False, "detail": detail})

    except Exception as e:
        log.error(f"驗證 API 金鑰時發生伺服器內部錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")


class ApiKeyPayload(BaseModel):
    api_key: str

@app.post("/api/youtube/models")
async def get_youtube_models(payload: ApiKeyPayload):
    """
    獲取可用的 Gemini 模型列表。
    現在接收一個包含 API 金鑰的 POST 請求。
    """
    # 在模擬模式下，回傳一個固定的假列表
    if IS_MOCK_MODE:
        return {
            "models": [
                {"id": "gemini-pro-mock", "name": "Gemini Pro (模擬)"},
                {"id": "gemini-1.5-flash-mock", "name": "Gemini 1.5 Flash (模擬)"}
            ]
        }

    # 真實模式下，從 gemini_processor.py 獲取
    try:
        if not payload.api_key:
            raise HTTPException(status_code=400, detail="請求中未提供 API 金鑰。")

        log.info(f"收到來自前端的 API 金鑰，將其用於獲取模型列表。")

        tool_script_path = ROOT_DIR / "src" / "tools" / "gemini_processor.py"
        cmd = [sys.executable, str(tool_script_path), "--command=list_models"]

        # JULES DEBUG (2025-08-31): 根據最新分析報告，此處是修復模型載入失敗的關鍵。
        # 舊的邏輯可能依賴了不穩定的、跨請求的環境變數。
        # 新的邏輯明確地將從 POST request body 中收到的 api_key 設定到子程序的環境變數中，
        # 確保了每次呼叫都使用正確的憑證。
        env = os.environ.copy()
        env["GOOGLE_API_KEY"] = payload.api_key

        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8', env=env)
        models = json.loads(result.stdout)
        return {"models": models}
    except subprocess.CalledProcessError as e:
        stderr_log = e.stderr.strip()
        log.error(f"獲取 Gemini 模型列表失敗，可能是因為 API 金鑰無效。Stderr: {stderr_log}")
        # 將更詳細的錯誤訊息傳回給前端
        if "API Key not found" in stderr_log:
            detail_message = "API 金鑰遺失。請確認後端已正確接收金鑰。"
        elif "API key not valid" in stderr_log:
            detail_message = "API 金鑰無效。請檢查您的金鑰。"
        else:
            detail_message = "無法使用提供的 API 金鑰獲取模型列表，請檢查金鑰權限或網路連線。"
        raise HTTPException(status_code=401, detail=detail_message)
    except Exception as e:
        log.error(f"獲取 Gemini 模型列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法獲取 Gemini 模型列表。")


@app.post("/api/youtube/process", status_code=202)
async def process_youtube_urls(request: Request):
    """
    接收 YouTube URL，並根據前端傳來的參數，建立對應的下載和 AI 分析任務。
    """
    payload = await request.json()
    requests_list = payload.get("requests", [])

    # JULES'S FIX: 為了相容舊的 local_run.py 測試腳本
    if not requests_list and "urls" in payload:
        log.warning("偵測到舊版的 'urls' 負載格式，正在進行相容處理。")
        requests_list = [{"url": url, "filename": None} for url in payload.get("urls", [])]


    # 新的彈性參數
    model = payload.get("model")
    tasks_to_run = payload.get("tasks", "summary,transcript") # e.g., "summary,transcript,translate"
    output_format = payload.get("output_format", "html") # "html" or "txt"
    download_only = payload.get("download_only", False)
    download_type = payload.get("download_type", "audio") # JULES'S NEW FEATURE
    api_key = payload.get("api_key") # 實現無狀態，從請求中直接獲取金鑰

    if not requests_list:
        # 在加入相容性邏輯後，更新錯誤訊息
        raise HTTPException(status_code=400, detail="請求中必須包含 'requests' 或 'urls'。")
    if not download_only and not model:
        raise HTTPException(status_code=400, detail="執行 AI 分析時必須提供 'model'。")
    if not download_only and not api_key:
        raise HTTPException(status_code=401, detail="執行 AI 分析時必須提供 'api_key'。")


    tasks = []
    for req_item in requests_list:
        url = req_item.get("url")
        filename = req_item.get("filename")

        if not url or not url.strip():
            continue

        task_id = str(uuid.uuid4())

        if download_only:
            # JULES'S NEW FEATURE: Pass download_type to payload
            task_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": filename, "download_type": download_type}
            db_client.add_task(task_id, json.dumps(task_payload), task_type='youtube_download_only')
            tasks.append({"url": url, "task_id": task_id})
        else:
            download_task_id = task_id
            process_task_id = str(uuid.uuid4())

            # JULES'S NEW FEATURE: Pass download_type to download payload
            download_payload = {"url": url, "output_dir": str(UPLOADS_DIR), "custom_filename": filename, "download_type": download_type}
            # 將所有新參數存入 process 任務的 payload
            process_payload = {
                "model": model,
                "output_dir": "transcripts",
                "tasks": tasks_to_run,
                "output_format": output_format,
                "api_key": api_key # 將金鑰存入任務酬載
            }

            db_client.add_task(download_task_id, json.dumps(download_payload), task_type='youtube_download')
            db_client.add_task(process_task_id, json.dumps(process_payload), task_type='gemini_process', depends_on=download_task_id)

            # JULES'S FIX: Return both task IDs so the frontend can track the full chain.
            tasks.append({
                "url": url,
                "task_id": download_task_id, # For display and initial tracking
                "final_task_id": process_task_id, # For listening to the final result
                "task_type": "youtube_process_chain"
            })

    return JSONResponse(content={"message": f"已為 {len(tasks)} 個 URL 建立處理任務。", "tasks": tasks})


def trigger_model_download(model_size: str, loop: asyncio.AbstractEventLoop):
    """
    在一個單獨的執行緒中執行模型下載，並透過 WebSocket 回報結果。
    這個版本會逐行讀取 stdout 來獲取即時的 JSON 進度更新。
    """
    def _download_in_thread():
        log.info(f"🧵 [執行緒] 開始下載模型: {model_size}")
        try:
            tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE else "transcriber.py")
            cmd = [sys.executable, str(tool_script_path), "--command=download", f"--model_size={model_size}"]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1 # Line-buffered
            )

            # 逐行讀取 stdout 以獲取進度更新
            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        # 建立 WebSocket 訊息
                        message = {
                            "type": "DOWNLOAD_STATUS",
                            "payload": {
                                "model": model_size,
                                "status": "downloading",
                                **data  # 這會包含 'type', 'percent', 'description' 等
                            }
                        }
                        asyncio.run_coroutine_threadsafe(manager.broadcast_json(message), loop)
                    except json.JSONDecodeError:
                        log.warning(f"[執行緒] 無法解析來自 transcriber 的下載進度 JSON: {line}")

            process.wait() # 等待程序結束

            # 根據程序的返回碼決定最終狀態
            if process.returncode == 0:
                log.info(f"✅ [執行緒] 模型 '{model_size}' 下載成功。")
                message = {
                    "type": "DOWNLOAD_STATUS",
                    "payload": {"model": model_size, "status": "completed", "progress": 100}
                }
            else:
                stderr_output = process.stderr.read() if process.stderr else "N/A"
                log.error(f"❌ [執行緒] 模型 '{model_size}' 下載失敗。 Stderr: {stderr_output}")
                message = {
                    "type": "DOWNLOAD_STATUS",
                    "payload": {"model": model_size, "status": "failed", "error": stderr_output}
                }

            asyncio.run_coroutine_threadsafe(manager.broadcast_json(message), loop)

        except Exception as e:
            log.error(f"❌ [執行緒] 下載執行緒中發生嚴重錯誤: {e}", exc_info=True)
            message = {
                "type": "DOWNLOAD_STATUS",
                "payload": {"model": model_size, "status": "failed", "error": str(e)}
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(message), loop)

    # 建立並啟動執行緒
    thread = threading.Thread(target=_download_in_thread)
    thread.start()


def trigger_transcription(task_id: str, file_path: str, model_size: str, language: Optional[str], beam_size: int, loop: asyncio.AbstractEventLoop, original_filename: Optional[str] = None):
    """
    在一個單獨的執行緒中執行轉錄，並透過 WebSocket 即時串流結果。
    """
    def _transcribe_in_thread():
        display_name = original_filename or file_path
        log.info(f"🧵 [執行緒] 開始處理轉錄任務: {task_id}，檔案: {display_name}")

        # 問題二：將所有輸出統一到 uploads 目錄下，以便提供靜態檔案服務
        output_dir = UPLOADS_DIR / "transcripts"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file_path = output_dir / f"{task_id}.txt"

        try:
            force_mock = os.environ.get("FORCE_MOCK_TRANSCRIBER") == "true"
            tool_script_path = ROOT_DIR / "src" / "tools" / ("mock_transcriber.py" if IS_MOCK_MODE or force_mock else "transcriber.py")
            cmd = [
                sys.executable,
                str(tool_script_path),
                "--command=transcribe",
                f"--audio_file={file_path}",
                f"--output_file={output_file_path}", # 使用新的路徑
                f"--model_size={model_size}",
            ]
            if language:
                cmd.append(f"--language={language}")
            cmd.append(f"--beam_size={beam_size}")

            log.info(f"執行轉錄指令: {' '.join(map(str, cmd))}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1
            )

            start_message_filename = original_filename or Path(file_path).name
            start_message = {
                "type": "TRANSCRIPTION_STATUS",
                "payload": {"task_id": task_id, "status": "starting", "filename": start_message_filename}
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(start_message), loop)

            if process.stdout:
                for line in iter(process.stdout.readline, ''):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "segment":
                            message = {
                                "type": "TRANSCRIPTION_UPDATE",
                                "payload": {"task_id": task_id, **data}
                            }
                            asyncio.run_coroutine_threadsafe(manager.broadcast_json(message), loop)
                    except json.JSONDecodeError:
                        log.warning(f"[執行緒] 無法解析來自 transcriber 的 JSON 行: {line}")

            process.wait()

            if process.returncode == 0:
                log.info(f"✅ [執行緒] 轉錄任務 '{task_id}' 成功完成。")
                final_transcript = output_file_path.read_text(encoding='utf-8').strip()

                # 問題二：將檔案系統路徑轉換為可存取的 URL
                final_result_obj = {
                    "transcript": final_transcript,
                    "transcript_path": convert_to_media_url(str(output_file_path)),
                    "output_path": convert_to_media_url(str(output_file_path)) # 增加一個通用的 output_path
                }
                db_client.update_task_status(task_id, 'completed', json.dumps(final_result_obj))
                log.info(f"✅ [執行緒] 已將任務 {task_id} 的狀態和結果更新至資料庫。")

                final_message = {
                    "type": "TRANSCRIPTION_STATUS",
                    "payload": {"task_id": task_id, "status": "completed", "result": final_result_obj}
                }
            else:
                stderr_output = process.stderr.read() if process.stderr else "N/A"
                log.error(f"❌ [執行緒] 轉錄任務 '{task_id}' 失敗。返回碼: {process.returncode}。Stderr: {stderr_output}")
                final_message = {
                    "type": "TRANSCRIPTION_STATUS",
                    "payload": {"task_id": task_id, "status": "failed", "error": stderr_output}
                }

            asyncio.run_coroutine_threadsafe(manager.broadcast_json(final_message), loop)

        except Exception as e:
            log.error(f"❌ [執行緒] 轉錄執行緒中發生嚴重錯誤: {e}", exc_info=True)
            error_message = {
                "type": "TRANSCRIPTION_STATUS",
                "payload": {"task_id": task_id, "status": "failed", "error": str(e)}
            }
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(error_message), loop)

    thread = threading.Thread(target=_transcribe_in_thread)
    thread.start()


def trigger_youtube_processing(task_id: str, loop: asyncio.AbstractEventLoop):
    """在一個單獨的執行緒中執行 YouTube 處理流程（已更新為彈性模式）。"""
    def _process_in_thread():
        log.info(f"🧵 [執行緒] 開始處理 YouTube 任務鏈，起始 ID: {task_id}")

        task_info = db_client.get_task_status(task_id)
        if not task_info:
            log.error(f"❌ [執行緒] 找不到起始任務 {task_id}")
            return

        task_type = task_info.get('type')
        dependent_task_id = None

        try:
            payload = json.loads(task_info['payload'])
            url = payload['url']
            custom_filename = payload.get("custom_filename")
            download_type = payload.get("download_type", "audio")

            asyncio.run_coroutine_threadsafe(manager.broadcast_json({
                "type": "YOUTUBE_STATUS",
                "payload": {"task_id": task_id, "status": "downloading", "message": f"正在下載 ({download_type}): {url}", "task_type": task_type}
            }), loop)

            # JULES DEBUG (2025-08-31): 為了 E2E 測試的穩定性，新增 mock URL 判斷
            if url.startswith("mock://"):
                downloader_script_path = ROOT_DIR / "src" / "tools" / "mock_downloader_for_test.py"
            else:
                downloader_script_path = ROOT_DIR / "src" / "tools" / ("mock_youtube_downloader.py" if IS_MOCK_MODE else "youtube_downloader.py")

            cmd_dl = [sys.executable, str(downloader_script_path), "--url", url, "--output-dir", str(UPLOADS_DIR), "--download-type", download_type]
            if custom_filename:
                cmd_dl.extend(["--custom-filename", custom_filename])

            cookies_path = UPLOADS_DIR / "cookies.txt"
            if cookies_path.is_file():
                log.info(f"發現 cookies.txt，將其用於下載。")
                cmd_dl.extend(["--cookies-file", str(cookies_path)])

            proc_env = os.environ.copy()
            # JULES'S FIX (2025-08-30): 重構 I/O 處理以解決死鎖問題
            # 舊的寫法是逐行讀取 stderr，但如果 stdout 的緩衝區被填滿，子程序會被阻塞，
            # 而父程序卻在等待 stderr，從而導致死鎖。
            #
            # 新的寫法使用 communicate()，它會安全地讀取兩個流直到程序結束，
            # 雖然會失去即時的進度回報，但能完全避免死鎖，確保任務能正確完成。
            # 這是根據 POC 成功案例的模式進行的重構。
            process_dl = subprocess.Popen(
                cmd_dl,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                env=proc_env
            )

            # communicate() 會讀取所有輸出直到程序結束，並返回結果。
            # 這能有效避免緩衝區填滿導致的死鎖。
            stdout_output, stderr_output = process_dl.communicate()

            # 在程序結束後，檢查返回碼
            if process_dl.returncode != 0:
                # 將 stderr 的內容包含在錯誤訊息中，以便除錯
                log.error(f"❌ [執行緒] youtube_downloader.py 執行失敗。Stderr: {stderr_output}")
                # 我們從 stdout 中解析 JSON，因為即使失敗，腳本也會輸出一個錯誤 JSON
                # 但如果 stdout 是空的，就使用 stderr 作為錯誤訊息
                if stdout_output:
                    raise RuntimeError(stdout_output)
                else:
                    raise RuntimeError(f"youtube_downloader.py 執行失敗，返回碼 {process_dl.returncode}。錯誤: {stderr_output}")

            # 如果成功，stdout 應該包含最終的 JSON 結果
            download_result = json.loads(stdout_output)
            media_file_path = download_result['output_path'] # This is an absolute path
            video_title = download_result.get('video_title', '無標題影片')
            log.info(f"✅ [執行緒] YouTube 媒體下載完成: {media_file_path}")

            if task_type == 'youtube_download_only':
                # 問題二：將檔案系統路徑轉換為可存取的 URL
                download_result['output_path'] = convert_to_media_url(download_result['output_path'])
                db_client.update_task_status(task_id, 'completed', json.dumps(download_result))
                log.info(f"✅ [執行緒] '僅下載媒體' 任務 {task_id} 完成。")
                asyncio.run_coroutine_threadsafe(manager.broadcast_json({
                    "type": "YOUTUBE_STATUS",
                    "payload": {"task_id": task_id, "status": "completed", "result": download_result, "task_type": "download_only"}
                }), loop)
                return

            db_client.update_task_status(task_id, 'completed', json.dumps(download_result))
            dependent_task_id = db_client.find_dependent_task(task_id)
            if not dependent_task_id:
                raise ValueError(f"找不到依賴於下載任務 {task_id} 的 gemini_process 任務")

            process_task_info = db_client.get_task_status(dependent_task_id)
            process_payload = json.loads(process_task_info['payload'])
            model = process_payload['model']
            tasks_to_run = process_payload.get('tasks', 'summary,transcript')
            output_format = process_payload.get('output_format', 'html')
            api_key = process_payload.get('api_key') # 從任務酬載中讀取金鑰

            log.info(f"執行 Gemini 分析，任務: '{tasks_to_run}', 格式: '{output_format}'")
            asyncio.run_coroutine_threadsafe(manager.broadcast_json({
                "type": "YOUTUBE_STATUS",
                "payload": {"task_id": dependent_task_id, "status": "processing", "message": f"使用 {model} 進行 AI 分析...", "task_type": "gemini_process"}
            }), loop)

            processor_script_path = ROOT_DIR / "src" / "tools" / ("mock_gemini_processor.py" if IS_MOCK_MODE else "gemini_processor.py")
            # 問題二：將報告也輸出到 uploads 目錄下
            report_output_dir = UPLOADS_DIR / "reports"
            report_output_dir.mkdir(parents=True, exist_ok=True)

            cmd_process = [
                sys.executable, str(processor_script_path),
                "--command=process",
                "--audio-file", media_file_path,
                "--model", model,
                "--output-dir", str(report_output_dir),
                "--video-title", video_title,
                "--tasks", tasks_to_run,
                "--output-format", output_format
            ]

            proc_env = os.environ.copy()
            if api_key:
                proc_env["GOOGLE_API_KEY"] = api_key # 將金鑰設定到子程序的環境變數中

            log.info(f"任務 {dependent_task_id}: 正要啟動 gemini_processor.py 子程序...")
            process_gemini = subprocess.Popen(
                cmd_process, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=proc_env
            )

            # JULES'S FIX (2025-09-01): Refactor I/O handling to prevent deadlocks.
            # Reading stderr line-by-line while stdout buffer might fill up is a classic deadlock scenario.
            # The safer approach is to use communicate() to get both streams after the process finishes.
            # This sacrifices real-time progress updates for stability and correctness, which is the right trade-off here.
            log.info(f"任務 {dependent_task_id}: 正在等待 gemini_processor.py 子程序完成...")
            stdout_output, stderr_output = process_gemini.communicate()
            log.info(f"任務 {dependent_task_id}: gemini_processor.py 子程序已結束。返回碼: {process_gemini.returncode}")

            if process_gemini.returncode != 0:
                # Log the full stderr for debugging purposes, then raise the error with stdout,
                # as the tool is designed to put the final error JSON in stdout.
                log.error(f"❌ [執行緒] gemini_processor.py 執行失敗。Stderr: {stderr_output}")
                if stdout_output:
                    raise RuntimeError(stdout_output)
                else:
                    raise RuntimeError(f"Gemini processor failed with exit code {process_gemini.returncode}. Stderr: {stderr_output}")

            process_result = json.loads(stdout_output)
            # 問題二：將結果中的所有檔案路徑轉換為 URL
            for key in ["output_path", "html_report_path", "pdf_report_path"]:
                 if key in process_result and process_result[key]:
                    process_result[key] = convert_to_media_url(process_result[key])

            db_client.update_task_status(dependent_task_id, '已完成', json.dumps(process_result))
            log.info(f"✅ [執行緒] Gemini AI 處理完成。")

            # JULES'S FIX (2025-08-31): 補上遺失的 WebSocket 廣播
            final_payload = {
                "task_id": dependent_task_id,
                "status": "completed",
                "task_type": "gemini_process",
                "result": process_result
            }
            update_message = {"type": "YOUTUBE_STATUS", "payload": final_payload}
            asyncio.run_coroutine_threadsafe(manager.broadcast_json(update_message), loop)
            log.info(f"✅ [執行緒] 已廣播 Gemini AI 任務完成訊息。")

        except Exception as e:
            log.error(f"❌ [執行緒] YouTube 處理鏈中發生錯誤: {e}", exc_info=True)
            failed_task_id = dependent_task_id if dependent_task_id else task_id
            error_payload = {"error": str(e)}
            try:
                error_json = json.loads(str(e))
                if isinstance(error_json, dict):
                    error_payload["error"] = error_json.get("error", str(e))
                    if error_json.get("error_code") == "AUTH_REQUIRED":
                        error_payload["error_type"] = "AUTH_REQUIRED"
            except (json.JSONDecodeError, TypeError):
                pass
            db_client.update_task_status(failed_task_id, 'failed', json.dumps(error_payload))
            asyncio.run_coroutine_threadsafe(manager.broadcast_json({
                "type": "YOUTUBE_STATUS",
                "payload": {"task_id": failed_task_id, "status": "failed", **error_payload}
            }), loop)

    thread = threading.Thread(target=_process_in_thread)
    thread.start()


@app.post("/api/debug/clear_tasks", status_code=200)
async def clear_all_tasks_endpoint():
    """
    [僅供測試] 清除所有任務，用於重置測試環境。
    """
    log.warning("⚠️ [僅供測試] 收到請求，將清除所有任務...")
    try:
        success = db_client.clear_all_tasks()
        if success:
            return {"status": "success", "message": "所有任務已成功清除。"}
        else:
            raise HTTPException(status_code=500, detail="在伺服器端清理任務時發生錯誤。")
    except Exception as e:
        log.error(f"❌ 清理任務的 API 端點發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/debug/latest_frontend_action_log")
async def get_latest_frontend_action_log():
    """
    [僅供測試] 獲取最新的前端操作日誌。
    用於 E2E 測試，以驗證日誌是否已成功寫入資料庫。
    """
    try:
        # 我們只關心來自 'frontend_action' logger 的日誌
        logs = db_client.get_system_logs(sources=['frontend_action'])
        if not logs:
            # 如果沒有日誌，返回一個清晰的空回應，而不是 404
            return JSONResponse(content={"latest_log": None}, status_code=200)

        # get_system_logs 按時間戳升序排序，所以最後一個就是最新的
        latest_log = logs[-1]
        return JSONResponse(content={"latest_log": latest_log})
    except Exception as e:
        log.error(f"❌ 查詢最新前端日誌時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="查詢最新前端日誌時發生內部錯誤")


@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            log.info(f"從 WebSocket 收到訊息: {data}")

            try:
                message = json.loads(data)
                msg_type = message.get("type")
                payload = message.get("payload", {})

                if msg_type == "DOWNLOAD_MODEL":
                    model_size = payload.get("model")
                    if model_size:
                        log.info(f"收到下載 '{model_size}' 模型的請求。")
                        await manager.broadcast_json({
                            "type": "DOWNLOAD_STATUS",
                            "payload": {"model": model_size, "status": "starting", "progress": 0}
                        })
                        loop = asyncio.get_running_loop()
                        trigger_model_download(model_size, loop)
                    else:
                        await manager.broadcast_json({"type": "ERROR", "payload": "缺少模型大小參數"})

                elif msg_type == "START_TRANSCRIPTION":
                    task_id = payload.get("task_id")
                    if not task_id:
                        await manager.broadcast_json({"type": "ERROR", "payload": "缺少 task_id 參數"})
                        continue

                    task_info = db_client.get_task_status(task_id)
                    if not task_info:
                        await manager.broadcast_json({"type": "ERROR", "payload": f"找不到任務 {task_id}"})
                        continue

                    try:
                        task_payload = json.loads(task_info['payload'])
                        file_path = task_payload.get("input_file")
                        model_size = task_payload.get("model_size", "tiny")
                        language = task_payload.get("language")
                        beam_size = task_payload.get("beam_size", 5)
                        original_filename = task_payload.get("original_filename") # JULES'S FIX
                    except (json.JSONDecodeError, KeyError) as e:
                        await manager.broadcast_json({"type": "ERROR", "payload": f"解析任務 {task_id} 的 payload 失敗: {e}"})
                        continue

                    if not file_path:
                        await manager.broadcast_json({"type": "ERROR", "payload": "任務 payload 中缺少檔案路徑"})
                    else:
                        display_name = original_filename or file_path
                        log.info(f"收到開始轉錄 '{display_name}' 的請求 (來自任務 {task_id})。")
                        loop = asyncio.get_running_loop()
                        trigger_transcription(task_id, file_path, model_size, language, beam_size, loop, original_filename=original_filename)

                elif msg_type == "START_YOUTUBE_PROCESSING":
                    task_id = payload.get("task_id") # This is the download_task_id
                    if not task_id:
                        await manager.broadcast_json({"type": "ERROR", "payload": "缺少 task_id 參數"})
                        continue

                    log.info(f"收到開始處理 YouTube 任務鏈的請求 (起始任務 ID: {task_id})。")
                    loop = asyncio.get_running_loop()
                    trigger_youtube_processing(task_id, loop)

                else:
                    await manager.broadcast_json({
                        "type": "ECHO",
                        "payload": f"已收到未知類型的訊息: {msg_type}"
                    })

            except json.JSONDecodeError:
                log.error("收到了非 JSON 格式的 WebSocket 訊息。")
                await manager.broadcast_json({"type": "ERROR", "payload": "訊息必須是 JSON 格式"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        log.info("WebSocket 用戶端已離線。")
    except Exception as e:
        log.error(f"WebSocket 發生未預期錯誤: {e}", exc_info=True)
        # 確保在發生錯誤時也中斷連線
        if websocket in manager.active_connections:
            manager.disconnect(websocket)


@app.get("/api/health")
async def health_check():
    """提供一個簡單的健康檢查端點。"""
    return {"status": "ok", "message": "API Server is running."}




class AppStatePayload(BaseModel):
    key: str
    value: str

@app.post("/api/app_state", status_code=200)
async def set_app_state_endpoint(payload: AppStatePayload):
    """
    設定一個應用程式狀態值。
    """
    try:
        success = db_client.set_app_state(payload.key, payload.value)
        if success:
            # 廣播狀態變更
            await manager.broadcast_json({"type": "APP_STATE_UPDATE", "payload": {payload.key: payload.value}})
            return {"status": "success", "key": payload.key, "value": payload.value}
        else:
            raise HTTPException(status_code=500, detail="無法在資料庫中設定應用程式狀態。")
    except Exception as e:
        log.error(f"❌ 設定應用程式狀態時 API 出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="設定應用程式狀態時發生內部錯誤。")

@app.get("/api/app_state", response_class=JSONResponse)
async def get_all_app_states_endpoint():
    """
    獲取所有應用程式狀態值。
    """
    try:
        states = db_client.get_all_app_states()
        return JSONResponse(content=states)
    except Exception as e:
        log.error(f"❌ 獲取所有應用程式狀態時 API 出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取所有應用程式狀態時發生內部錯誤。")


@app.post("/api/internal/notify_task_update", status_code=200)
async def notify_task_update(payload: Dict):
    """
    一個內部端點，供 Worker 程序在任務完成時呼叫，
    以便透過 WebSocket 將更新廣播給前端。
    """
    task_id = payload.get("task_id")
    status = payload.get("status")
    result = payload.get("result")
    log.info(f"🔔 收到來自 Worker 的任務更新通知: Task {task_id} -> {status}")

    # JULES'S FIX: 查詢任務類型以發送正確的 WebSocket 訊息
    task_info = db_client.get_task_status(task_id)
    task_type = task_info.get("type", "transcribe") if task_info else "transcribe"

    message_type = "TRANSCRIPTION_STATUS"
    if "youtube" in task_type or "gemini" in task_type:
        message_type = "YOUTUBE_STATUS"

    log.info(f"根據任務類型 '{task_type}'，將使用 WebSocket 訊息類型: '{message_type}'")

    # 確保 result 是字典格式
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            log.warning(f"來自 worker 的任務 {task_id} 結果不是有效的 JSON 格式。")

    message = {
        "type": message_type,
        "payload": {
            "task_id": task_id,
            "status": status,
            "result": result,
            "task_type": task_type  # 將 task_type 也傳給前端
        }
    }
    await manager.broadcast_json(message)
    return {"status": "notification_sent"}


# --- 主程式啟動 ---
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="鳳凰音訊轉錄儀 API 伺服器")
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="伺服器監聽的埠號"
    )
    args, _ = parser.parse_known_args()

    # JULES: 移除此處的資料庫初始化呼叫。
    # 父程序 src/core/orchestrator.py 將會負責此事，以避免競爭條件。

    # JULES'S FIX: The database logging is now set up via the app's lifespan event.
    # setup_database_logging() is no longer needed here.

    log.info("🚀 啟動 API 伺服器 (v3)...")
    log.info(f"請在瀏覽器中開啟 http://127.0.0.1:{args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)
