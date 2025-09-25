import logging
import sys
from pathlib import Path
import httpx

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- 路徑修正 ---
# 將服務的根目錄新增到 Python 的搜尋路徑中，以便找到本地模組
SERVICE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SERVICE_ROOT))

# --- 本地模組匯入 ---
from tools.url_extractor import parse_chat_log
from db.client import DBClient

# --- 日誌與樣板設定 ---
log = logging.getLogger(__name__)
# 模板檔案位於主專案的 src/static 目錄下
PROJECT_ROOT = SERVICE_ROOT.parent.parent
templates = Jinja2Templates(directory=str(PROJECT_ROOT / "src" / "static"))

# --- FastAPI 應用 ---
app = FastAPI(title="Core Service")

# --- 依賴注入 ---
def get_db():
    """提供一個 DBClient 實例的依賴項。"""
    # 每次請求都建立一個新的客戶端實例是安全的，因為 httpx 會在內部管理連線池。
    return DBClient()

# --- Pydantic 模型 ---
class UrlExtractionRequest(BaseModel):
    text: str

# --- API 端點 ---
@app.post("/api/page1/extract_urls", status_code=200, tags=["Page 1 API"])
async def extract_urls_endpoint(payload: UrlExtractionRequest, db: DBClient = Depends(get_db)):
    """
    (從主 API 伺服器遷移)
    接收文字，解析出 URL，並透過 DBClient 將它們儲存到資料庫。
    """
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    try:
        parsed_data = parse_chat_log(source_text)
        if parsed_data:
            db.add_new_urls(parsed_data, source_text)
        # 即使沒有新增資料，也回傳解析出的內容讓前端確認
        return JSONResponse(content=parsed_data)
    except Exception as e:
        log.error(f"在 core_service 中處理網址提取請求時發生錯誤: {e}", exc_info=True)
        # 區分網路錯誤和內部錯誤
        if isinstance(e, (ConnectionError, httpx.RequestError)):
             raise HTTPException(status_code=503, detail=f"核心服務無法連線至資料庫管理器: {e}")
        raise HTTPException(status_code=500, detail=f"核心服務內部錯誤: {str(e)}")

# --- UI 頁面路由 ---
# (從 ui.py 遷移過來的所有路由)
@app.get("/menu", response_class=HTMLResponse, tags=["UI"])
async def serve_menu(request: Request):
    return templates.TemplateResponse("menu.html", {"request": request})

@app.get("/page1", response_class=HTMLResponse, tags=["UI"])
async def serve_page1_container(request: Request):
    return templates.TemplateResponse("page1.html", {"request": request})

@app.get("/page2", response_class=HTMLResponse, tags=["UI"])
async def serve_page2(request: Request):
    return templates.TemplateResponse("page2_downloader.html", {"request": request})

@app.get("/page3", response_class=HTMLResponse, tags=["UI"])
async def serve_page3(request: Request):
    return templates.TemplateResponse("page3_processor.html", {"request": request})

@app.get("/page4_stage1_ai", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_stage1(request: Request):
    return templates.TemplateResponse("page4_stage1_ai.html", {"request": request})

@app.get("/page4_stage1_5_date", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_stage1_5(request: Request):
    return templates.TemplateResponse("page4_stage1_5_date.html", {"request": request})

@app.get("/page4_stage2_performance", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_stage2(request: Request):
    return templates.TemplateResponse("page4_stage2_performance.html", {"request": request})

@app.get("/page4_stage3_report", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_stage3(request: Request):
    return templates.TemplateResponse("page4_stage3_report.html", {"request": request})

@app.get("/page4_stage4_download", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_stage4(request: Request):
    return templates.TemplateResponse("page4_stage4_download.html", {"request": request})

@app.get("/page5", response_class=HTMLResponse, tags=["UI"])
async def serve_page5(request: Request):
    return templates.TemplateResponse("page5_backup.html", {"request": request})

@app.get("/page6", response_class=HTMLResponse, tags=["UI"])
async def serve_page6(request: Request):
    return templates.TemplateResponse("page6_keys.html", {"request": request})

@app.get("/page7", response_class=HTMLResponse, tags=["UI"])
async def serve_page7(request: Request):
    return templates.TemplateResponse("page7_prompts.html", {"request": request})

@app.get("/prompts", response_class=HTMLResponse, tags=["UI"])
async def serve_prompts_ui(request: Request):
    return templates.TemplateResponse("prompts.html", {"request": request})

@app.get("/history", response_class=HTMLResponse, tags=["UI"])
async def serve_history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})

@app.get("/report/{file_id}", response_class=HTMLResponse, tags=["UI"])
async def serve_report_viewer(request: Request, file_id: int):
    return templates.TemplateResponse("report_viewer.html", {"request": request, "file_id": file_id})

@app.get("/page8", response_class=HTMLResponse, tags=["UI"])
async def serve_page8(request: Request):
    return templates.TemplateResponse("page8_file_details.html", {"request": request})

@app.get("/page9", response_class=HTMLResponse, tags=["UI"])
async def serve_page9(request: Request):
    return templates.TemplateResponse("page9_dashboard.html", {"request": request})

@app.get("/page10_service_test.html", response_class=HTMLResponse, tags=["UI"])
async def serve_page10(request: Request):
    return templates.TemplateResponse("page10_service_test.html", {"request": request})

@app.get("/line-extractor", response_class=HTMLResponse, tags=["UI"])
async def serve_line_extractor(request: Request):
    return templates.TemplateResponse("line_extractor.html", {"request": request})

@app.get("/page4_summary_center", response_class=HTMLResponse, tags=["UI"])
async def serve_page4_summary_center(request: Request):
    return templates.TemplateResponse("page4_summary_center.html", {"request": request})

@app.get("/page_bond", response_class=HTMLResponse, tags=["UI"])
async def serve_page_bond(request: Request):
    return templates.TemplateResponse("page_bond.html", {"request": request})