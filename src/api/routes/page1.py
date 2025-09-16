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

from tools.url_extractor import parse_chat_log, save_urls_to_db
from db.database import get_db_connection

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter() # REMOVED prefix

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

@router.get("/api/page1/overview_data")
async def get_overview_data(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    count_only: bool = Query(False)
):
    # 修正：將 'date' 欄位更正為 'message_date'
    query = "SELECT id, url, author, message_date as date FROM extracted_urls"
    filters = []
    params = []

    # 修正：篩選條件也應使用 'message_date'
    if start_date:
        filters.append("message_date >= ?")
        params.append(start_date)
    if end_date:
        filters.append("message_date <= ?")
        params.append(end_date)

    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY created_at DESC"

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            if count_only:
                count_query = f"SELECT COUNT(*) FROM ({query})"
                cursor.execute(count_query, params)
                count = cursor.fetchone()[0]
                return {"count": count}

            cursor.execute(query, params)
            rows = cursor.fetchall()
            results = [{"id": r[0], "url": r[1], "author": r[2], "date": r[3]} for r in rows]
            return JSONResponse(content=results)
    except Exception as e:
        log.error(f"查詢總覽資料時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="資料庫查詢失敗")

@router.get("/api/page1/export")
async def export_data(
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None)
):
    # 修正：將 'date' 和 'time' 欄位更正為 'message_date' 和 'message_time'
    query = "SELECT message_date, message_time, author, url FROM extracted_urls"
    filters = []
    params = []
    if start_date and start_date != '未設定':
        filters.append("message_date >= ?")
        params.append(start_date)
    if end_date and end_date != '未設定':
        filters.append("message_date <= ?")
        params.append(end_date)
    if filters:
        query += " WHERE " + " AND ".join(filters)

    query += " ORDER BY message_date, message_time"

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
        output = df.to_csv(index=False, encoding='utf-8-sig')
        return Response(
            content=output,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"}
        )
    else:
        content = f"此為 {format} 格式的預留位置匯出。\n\n篩選範圍:\n開始日期: {start_date}\n結束日期: {end_date}\n\n資料內容:\n{df.to_string()}"
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=export.{format}.txt"}
        )
