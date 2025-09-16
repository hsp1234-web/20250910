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

@router.get("/api/page1/export")
async def export_data(
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: DBClient = Depends(get_db)
):
    """(V4 優化後) 使用 DBClient 獲取資料並匯出。"""
    try:
        # 獲取資料
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        # 將字典列表轉換為 DataFrame
        df = pd.DataFrame(results)
        # 為了匯出，將 'date' 欄位重新命名回 'message_date'
        if 'date' in df.columns:
            df.rename(columns={'date': 'message_date'}, inplace=True)
        # 確保匯出欄位的順序與舊版一致
        export_columns = ['message_date', 'author', 'url']
        # 有些紀錄可能沒有 message_time，所以這裡不加入
        df = df[export_columns]

    except Exception as e:
        log.error(f"匯出時讀取資料庫失敗: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
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
        # 對於純文字預留位置，明確使用 utf-8-sig 編碼以包含BOM，防止在 Windows 上出現亂碼
        content = f"此為 {format} 格式的預留位置匯出。\n\n篩選範圍:\n開始日期: {start_date or '未設定'}\n結束日期: {end_date or '未設定'}\n\n資料內容:\n{df.to_string()}"
        return Response(
            content=content.encode('utf-8-sig'),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=export.{format}.txt"}
        )
