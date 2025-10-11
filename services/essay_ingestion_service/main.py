# services/essay_ingestion_service/main.py
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional

# --- 核心邏輯模組匯入 ---
from .logic import parse_chat_log, save_parsed_data_to_db
from .document_analyzer import process_local_document

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service_main')

# --- 應用程式生命週期事件 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """在應用程式啟動時執行的生命週期事件。"""
    log.info("「小作文擷取服務」(無狀態版) 啟動中...")
    log.info("✅ 服務已就緒，可以開始接收請求。")
    yield
    log.info("「小作文擷取服務」正在關閉。")

# --- FastAPI 應用實例 ---
app = FastAPI(
    title="小作文擷取服務 (Essay Ingestion Service)",
    description="一個多功能微服務，用於：1. 解析 LINE 聊天紀錄、2. 接收本地文件並進行圖文分析。",
    version="3.0.0", # 版本升級，反映無狀態重構
    lifespan=lifespan
)

# --- 資料模型 (Pydantic Models) ---

# 模型 for /ingest (聊天紀錄解析)
class IngestRequest(BaseModel):
    text: str

class InsertedItem(BaseModel):
    id: int
    url: str
    title: Optional[str] = None
    author: Optional[str] = None
    message_date: Optional[str] = None

class IngestResponse(BaseModel):
    message: str
    inserted_count: int
    inserted_items: List[InsertedItem]

# 簡化後的模型，此服務只關心檔案路徑
class ProcessLocalDocumentRequest(BaseModel):
    file_path: str

# --- API 端點 ---

# 端點 1: /ingest (現有功能)
@app.post("/ingest", response_model=IngestResponse, tags=["聊天紀錄解析"])
async def ingest_text(request: IngestRequest):
    """
    接收文字，解析後存入資料庫，並回傳新增的項目列表。
    """
    log.info("接收到 /ingest 請求。")
    if not request.text or not request.text.strip():
        log.warning("請求的文字內容為空。")
        raise HTTPException(status_code=400, detail="文字內容不可為空。")

    try:
        log.info("開始解析文字...")
        parsed_data = parse_chat_log(request.text)
        if not parsed_data:
            log.info("從文字中未解析出任何有效資料。")
            return IngestResponse(message="未解析出有效資料。", inserted_count=0, inserted_items=[])

        log.info(f"解析出 {len(parsed_data)} 筆資料，準備存入資料庫...")
        inserted_items = save_parsed_data_to_db(parsed_data, source_text=request.text)
        inserted_count = len(inserted_items)

        return IngestResponse(
            message=f"處理完成，成功新增 {inserted_count} 筆資料。",
            inserted_count=inserted_count,
            inserted_items=inserted_items
        )
    except Exception as e:
        log.error(f"處理 /ingest 請求時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"內部伺服器錯誤: {e}")

# --- 新的、拆分後的端點 ---

class ExtractContentRequest(BaseModel):
    file_path: str

class ExtractContentResponse(BaseModel):
    extracted_text: str
    image_paths: List[str]

class AnalyzeTextRequest(BaseModel):
    text_content: str

@app.post("/extract-content", response_model=ExtractContentResponse, tags=["文件圖文分析 (V2)"])
async def extract_content_endpoint(request: ExtractContentRequest):
    """
    步驟 1: 接收檔案路徑，僅執行內容提取（文字和圖片）。
    """
    log.info(f"接收到 /extract-content 請求，路徑: {request.file_path}")
    try:
        # 這裡我們需要一個只執行內容提取的函式
        from .content_extractor import extract_content
        # 注意：content_extractor 需要一個輸出目錄來存放圖片
        # 我們可以設定一個預設或暫存的目錄
        output_dir = "services/essay_ingestion_service/downloads"
        content_data = await asyncio.to_thread(extract_content, request.file_path, output_dir)
        if content_data is None:
            raise FileNotFoundError(f"無法處理或找不到檔案: {request.file_path}")
        return ExtractContentResponse(
            extracted_text=content_data.get("text", ""),
            image_paths=content_data.get("image_paths", [])
        )
    except FileNotFoundError as e:
        log.error(f"檔案未找到: {e}", exc_info=True)
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.error(f"提取內容時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"提取內容時發生內部錯誤: {e}")


@app.post("/analyze-text", response_model=Dict[str, Any], tags=["文件圖文分析 (V2)"])
async def analyze_text_endpoint(request: AnalyzeTextRequest):
    """
    步驟 2: 接收文字內容，僅執行 AI 分析。
    """
    log.info(f"接收到 /analyze-text 請求，內容長度: {len(request.text_content)} 字元。")
    if not request.text_content:
        log.warning("請求的文字內容為空，無法進行分析。")
        # 即使內容為空，也回傳一個符合成功結構的空結果，讓呼叫方可以一致地處理
        return {}

    try:
        from .document_analyzer import analyze_text_with_llm
        analysis_result = await analyze_text_with_llm(request.text_content)
        return analysis_result
    except ConnectionError as e:
        log.error(f"下游服務連線錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        log.error(f"分析文字時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"分析文字時發生內部錯誤: {e}")

# --- 啟動配置 ---
if __name__ == "__main__":
    log.info("準備以獨立模式啟動「小作文擷取服務」...")
    uvicorn.run(app, host="0.0.0.0", port=8001)