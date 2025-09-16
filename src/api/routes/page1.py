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

SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log, save_urls_to_db
from db.database import get_db_connection

log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter(prefix="/page1", tags=["Page 1 - Data Ingestion and Overview"])

class UrlExtractionRequest(BaseModel):
    text: str

# --- HTML 頁面路由 ---
@router.get("/ingestion", response_class=HTMLResponse)
async def get_ingestion_page(request: Request):
    return templates.TemplateResponse("page1_sub_ingestion.html", {"request": request})

@router.get("/overview", response_class=HTMLResponse)
async def get_overview_page(request: Request):
    return templates.TemplateResponse("page1_sub_overview.html", {"request": request})

@router.get("/export", response_class=HTMLResponse)
async def get_export_page(request: Request):
    return templates.TemplateResponse("page1_sub_export.html", {"request": request})

# --- API 端點 ---
@router.post("/api/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest):
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    try:
        parsed_data = parse_chat_log(source_text)
        if parsed_data:
            with get_db_connection() as conn:
                save_urls_to_db(parsed_data, source_text, conn)
        return JSONResponse(content=parsed_data)
    except Exception as e:
        log.error(f"處理網址提取請求時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/overview_data")
async def get_overview_data(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    count_only: bool = Query(False)
):
    query = "SELECT url, author, date FROM extracted_urls"
    filters = []
    params = []

    if start_date:
        filters.append("date >= ?")
        params.append(start_date)
    if end_date:
        filters.append("date <= ?")
        params.append(end_date)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if count_only:
                cursor.execute(f"SELECT COUNT(*) FROM ({query})", params)
                count = cursor.fetchone()[0]
                return {"count": count}

            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [{"url": r[0], "author": r[1], "date": r[2]} for r in rows]
            return JSONResponse(content=results)
    except Exception as e:
        log.error(f"查詢總覽資料時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="資料庫查詢失敗")

@router.get("/api/export")
async def export_data(
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    # 基本上與 overview_data 相同的查詢邏輯
    query = "SELECT date, time, author, url FROM extracted_urls"
    filters = []
    params = []
    if start_date and start_date != '未設定':
        filters.append("date >= ?")
        params.append(start_date)
    if end_date and end_date != '未設定':
        filters.append("date <= ?")
        params.append(end_date)
    if filters:
        query += " WHERE " + " AND ".join(filters)

    try:
        with get_db_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
    except Exception as e:
        log.error(f"匯出時讀取資料庫失敗: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取資料庫失敗")

    if format == "excel":
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
        output = df.to_csv(index=False)
        return Response(
            content=output,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"}
        )
    # 其他格式 (PDF, DOCX, HTML) 的實作可以稍後加入
    # 為了簡化，我們先回傳一個錯誤訊息
    else:
        raise HTTPException(status_code=400, detail=f"不支援的匯出格式: {format}")
