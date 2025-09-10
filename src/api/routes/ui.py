from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- 路徑與樣板設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# --- UI 頁面路由 ---

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

@router.get("/prompts", response_class=HTMLResponse)
async def serve_prompts_ui(request: Request):
    return templates.TemplateResponse("prompts.html", {"request": request})

@router.get("/history", response_class=HTMLResponse)
async def serve_history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})
