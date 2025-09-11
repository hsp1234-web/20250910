from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- 路徑與樣板設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# --- UI 頁面路由 ---

@router.get("/menu", response_class=HTMLResponse)
async def serve_menu(request: Request):
    return templates.TemplateResponse("menu.html", {"request": request})


@router.get("/page1", response_class=HTMLResponse)
async def serve_page1(request: Request):
    return templates.TemplateResponse("page1_ingestion.html", {"request": request})

@router.get("/page2", response_class=HTMLResponse)
async def serve_page2(request: Request):
    return templates.TemplateResponse("page2_downloader.html", {"request": request})

@router.get("/page3", response_class=HTMLResponse)
async def serve_page3(request: Request):
    return templates.TemplateResponse("page3_processor.html", {"request": request})

@router.get("/page4", response_class=HTMLResponse)
async def serve_page4(request: Request):
    return templates.TemplateResponse("page4_analyzer.html", {"request": request})

@router.get("/page5", response_class=HTMLResponse)
async def serve_page5(request: Request):
    return templates.TemplateResponse("page5_backup.html", {"request": request})

@router.get("/page6", response_class=HTMLResponse)
async def serve_page6(request: Request):
    return templates.TemplateResponse("page6_keys.html", {"request": request})

@router.get("/page7", response_class=HTMLResponse)
async def serve_page7(request: Request):
    return templates.TemplateResponse("page7_prompts.html", {"request": request})

@router.get("/page8", response_class=HTMLResponse)
async def serve_page8(request: Request):
    return templates.TemplateResponse("page8_autotrader.html", {"request": request})

@router.get("/prompts", response_class=HTMLResponse)
async def serve_prompts_ui(request: Request):
    return templates.TemplateResponse("prompts.html", {"request": request})

@router.get("/history", response_class=HTMLResponse)
async def serve_history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})


@router.get("/report/{file_id}", response_class=HTMLResponse)
async def serve_report_viewer(request: Request, file_id: int):
    """
    提供新的報告檢視器頁面。
    我們將 file_id 傳遞給模板，雖然模板本身不直接使用它，
    但前端的 JavaScript 可以從 URL 中讀取它。
    """
    return templates.TemplateResponse("report_viewer.html", {"request": request, "file_id": file_id})
