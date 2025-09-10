import logging
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates


# --- 路徑與樣板設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
# 專案根目錄
ROOT_DIR = SRC_DIR.parent
DOWNLOAD_DIR = ROOT_DIR / "downloads"

templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()
log = logging.getLogger(__name__)


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

@router.get("/prompts", response_class=HTMLResponse)
async def serve_prompts_ui(request: Request):
    return templates.TemplateResponse("prompts.html", {"request": request})

@router.get("/history", response_class=HTMLResponse)
async def serve_history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})


# --- 檔案服務端點 ---

@router.get("/downloads/{file_path:path}", tags=["UI Assets"])
async def serve_downloaded_file(file_path: str):
    """
    安全地提供從 'downloads' 資料夾下載的檔案。
    這個端點是為了讓前端可以直接預覽下載的圖片等內容。
    """
    try:
        # 安全地組合路徑，防止路徑遍歷 (directory traversal) 攻擊
        # .resolve() 會解析路徑，處理 ".." 等符號
        safe_path = DOWNLOAD_DIR.joinpath(file_path).resolve()

        # 再次確認解析後的路徑確實位於我們預期的 DOWNLOAD_DIR 目錄下
        if not str(safe_path).startswith(str(DOWNLOAD_DIR)):
            log.warning(f"偵測到潛在的路徑遍歷攻擊: 請求路徑 {file_path}, 解析後路徑 {safe_path}")
            raise HTTPException(status_code=403, detail="禁止存取。")

        if safe_path.is_file():
            return FileResponse(str(safe_path))
        else:
            log.warning(f"請求的下載檔案不存在: {safe_path}")
            # 回傳 JSON 錯誤，方便前端處理
            return JSONResponse(status_code=404, content={"detail": "找不到檔案。"})

    except Exception as e:
        log.error(f"服務下載檔案時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")
