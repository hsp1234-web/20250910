import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# --- 路徑與樣板設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_DIR = str(SRC_DIR / "static")
templates = Jinja2Templates(directory=STATIC_DIR)
router = APIRouter()

# --- UI 頁面路由 ---

@router.get("/menu", response_class=HTMLResponse)
async def serve_menu(request: Request):
    return templates.TemplateResponse("menu.html", {"request": request})


@router.get("/page1", response_class=HTMLResponse)
async def serve_page1_container(request: Request):
    """ 提供包含 IFrame 的主容器頁面 """
    return templates.TemplateResponse("page1.html", {"request": request})

@router.get("/page2", response_class=HTMLResponse)
async def serve_page2(request: Request):
    return templates.TemplateResponse("page2_downloader.html", {"request": request})

@router.get("/page3", response_class=HTMLResponse)
async def serve_page3(request: Request):
    return templates.TemplateResponse("page3_processor.html", {"request": request})

@router.get("/page4_stage1_ai", response_class=HTMLResponse)
async def serve_page4_stage1(request: Request):
    return templates.TemplateResponse("page4_stage1_ai.html", {"request": request})

@router.get("/page4_stage1_5_date", response_class=HTMLResponse)
async def serve_page4_stage1_5(request: Request):
    return templates.TemplateResponse("page4_stage1_5_date.html", {"request": request})

@router.get("/page4_stage2_performance", response_class=HTMLResponse)
async def serve_page4_stage2(request: Request):
    return templates.TemplateResponse("page4_stage2_performance.html", {"request": request})

@router.get("/page4_stage3_report", response_class=HTMLResponse)
async def serve_page4_stage3(request: Request):
    return templates.TemplateResponse("page4_stage3_report.html", {"request": request})

@router.get("/page4_stage4_download", response_class=HTMLResponse)
async def serve_page4_stage4(request: Request):
    return templates.TemplateResponse("page4_stage4_download.html", {"request": request})

@router.get("/page5", response_class=HTMLResponse)
async def serve_page5(request: Request):
    return templates.TemplateResponse("page5_backup.html", {"request": request})

@router.get("/page6", response_class=HTMLResponse)
async def serve_page6(request: Request):
    return templates.TemplateResponse("page6_keys.html", {"request": request})

@router.get("/page7", response_class=HTMLResponse)
async def serve_page7(request: Request):
    return templates.TemplateResponse("page7_prompts.html", {"request": request})

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

@router.get("/page8", response_class=HTMLResponse)
async def serve_page8(request: Request):
    return templates.TemplateResponse("page8_file_details.html", {"request": request})

@router.get("/page9", response_class=HTMLResponse)
async def serve_page9(request: Request):
    return templates.TemplateResponse("page9_dashboard.html", {"request": request})


@router.get("/page10_service_test.html", response_class=HTMLResponse)
async def serve_page10(request: Request):
    return templates.TemplateResponse("page10_service_test.html", {"request": request})

@router.get("/line-extractor", response_class=HTMLResponse)
async def serve_line_extractor(request: Request):
    """ 提供獨立的 LINE 貼文批量整理工具頁面。 """
    return templates.TemplateResponse("line_extractor.html", {"request": request})


@router.get("/page4_summary_center", response_class=HTMLResponse)
async def serve_page4_summary_center(request: Request):
    """ 提供重點摘要中心頁面 """
    return templates.TemplateResponse("page4_summary_center.html", {"request": request})

@router.get("/page_bond", response_class=HTMLResponse)
async def serve_page_bond(request: Request):
    """ 提供債券分析頁面 """
    return templates.TemplateResponse("page_bond.html", {"request": request})


@router.get("/primary_dealer_analysis", response_class=HTMLResponse)
async def serve_primary_dealer_analysis(request: Request):
    """ 提供一級交易商分析儀表板頁面 """
    return templates.TemplateResponse("primary_dealer_analysis.html", {"request": request})


@router.get("/line_importer", tags=["UI"])
async def read_line_importer_page():
    """(Jules @ 2025-10-12) 提供 LINE 匯入工具頁面"""
    return FileResponse(os.path.join(STATIC_DIR, "line_importer.html"))

@router.get("/line_workflow_editor", tags=["UI"])
async def read_line_workflow_editor_page():
    """(Jules @ 2025-10-12) 提供新的 LINE 工作流編輯器頁面"""
    return FileResponse(os.path.join(STATIC_DIR, "line_workflow_editor.html"))

@router.get("/line_data_viewer", tags=["UI"])
async def read_line_data_viewer_page():
    """(Jules @ 2025-10-14) 提供新的 LINE 資料檢視器頁面"""
    return FileResponse(os.path.join(STATIC_DIR, "line_data_viewer.html"))

@router.get("/line_item_editor", tags=["UI"])
async def read_line_item_editor_page():
    """(Jules @ 2025-10-14) 提供新的 LINE 項目編輯器頁面"""
    return FileResponse(os.path.join(STATIC_DIR, "line_item_editor.html"))

@router.get("/line_workflow_history", tags=["UI"])
async def read_line_workflow_history_page():
    """(Jules @ 2025-10-14) 提供新的 LINE 工作流歷史頁面"""
    return FileResponse(os.path.join(STATIC_DIR, "line_workflow_history.html"))