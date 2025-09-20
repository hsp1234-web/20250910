import logging
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd
from io import BytesIO

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log
# V4 優化：移除舊的資料庫連線方式
# from db.database import get_db_connection
from fastapi import Depends
from db.client import DBClient
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

class UrlExtractionRequest(BaseModel):
    text: str

# --- HTML 頁面路由 ---
@router.get("/page1/ingestion", response_class=HTMLResponse)
async def get_ingestion_page(request: Request):
    return templates.TemplateResponse("page1_sub_ingestion.html", {"request": request})

@router.get("/page1/overview", response_class=HTMLResponse)
async def get_overview_page(request: Request):
    return templates.TemplateResponse("page1_sub_overview.html", {"request": request})

@router.get("/page1/export", response_class=HTMLResponse)
async def get_export_page(request: Request):
    return templates.TemplateResponse("page1_sub_export.html", {"request": request})

# --- API 端點 ---
@router.post("/api/page1/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest, db: DBClient = Depends(get_db)):
    """(V4 優化後) 提取 URL 並使用 DBClient 儲存。"""
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    try:
        parsed_data = parse_chat_log(source_text)
        if parsed_data:
            # 使用新的 DBClient 方法
            db.add_new_urls(parsed_data, source_text)
        # 即使沒有新增資料，也回傳解析出的內容讓前端確認
        return JSONResponse(content=parsed_data)
    except Exception as e:
        log.error(f"處理網址提取請求時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/page1/overview_data")
async def get_overview_data(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    count_only: bool = Query(False),
    db: DBClient = Depends(get_db)
):
    """(V4 優化後) 使用 DBClient 獲取總覽資料。"""
    try:
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        if count_only:
            return {"count": len(results)}
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"查詢總覽資料時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="資料庫查詢失敗")

from weasyprint import HTML
from docx import Document

@router.get("/api/page1/export")
async def export_data(
    request: Request, # V36.8: 加入 request 以便使用 templates
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: DBClient = Depends(get_db)
):
    """
    (V36.8 更新) 使用 DBClient 獲取資料並根據指定格式匯出。
    - 新增 HTML 和 PDF 匯出功能。
    - HTML/PDF 使用卡片式佈局。
    - 修正了 Excel 匯出的依賴問題。
    """
    try:
        # 獲取資料
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        # V36.8: 直接使用字典列表，不再轉換為 DataFrame，以便範本處理
        # 確保 'message_date' 欄位存在
        for r in results:
            if 'date' in r:
                r['message_date'] = r.pop('date')

    except Exception as e:
        log.error(f"匯出時讀取資料庫失敗: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="讀取資料庫失敗")

    if format == "excel":
        df = pd.DataFrame(results)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='資料匯出')
        output.seek(0)
        return Response(
            output.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=export.xlsx"}
        )
    elif format == "csv":
        df = pd.DataFrame(results)
        output = df.to_csv(index=False, encoding='utf-8-sig')
        return Response(
            content=output,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"}
        )
    elif format == "html":
        # V36.8: 實作 HTML 匯出
        html_content = templates.TemplateResponse(
            "export_cards.html",
            {
                "request": request,
                "data": results,
                "start_date": start_date,
                "end_date": end_date
            }
        ).body.decode("utf-8")
        return Response(
            content=html_content,
            media_type="text/html",
            headers={"Content-Disposition": "attachment; filename=export.html"}
        )
    elif format == "pdf":
        # V36.8: 實作 PDF 匯出
        html_content = templates.TemplateResponse(
            "export_cards.html",
            {
                "request": request,
                "data": results,
                "start_date": start_date,
                "end_date": end_date
            }
        ).body.decode("utf-8")

        pdf_output = BytesIO()
        HTML(string=html_content).write_pdf(pdf_output)
        pdf_output.seek(0)

        return Response(
            pdf_output.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=export.pdf"}
        )
    elif format == "docx":
        # V36.8.1: 新增 DOCX 匯出功能
        document = Document()
        document.add_heading('網址資料匯出', level=1)

        # 新增日期範圍資訊
        document.add_paragraph(f"篩選範圍: {start_date or '所有時間'} 至 {end_date or '所有時間'}")

        # 建立表格
        table = document.add_table(rows=1, cols=3)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = '日期'
        hdr_cells[1].text = '作者'
        hdr_cells[2].text = 'URL'

        # 填入資料
        for item in results:
            row_cells = table.add_row().cells
            row_cells[0].text = item.get('message_date', 'N/A')
            row_cells[1].text = item.get('author', 'N/A')
            row_cells[2].text = item.get('url', 'N/A')

        # 儲存至記憶體
        output = BytesIO()
        document.save(output)
        output.seek(0)

        return Response(
            output.read(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=export.docx"}
        )
    else:
        # 對於不支援的格式，回傳錯誤
        raise HTTPException(status_code=400, detail=f"不支援的匯出格式: {format}")
