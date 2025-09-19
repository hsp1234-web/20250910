import logging
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import pandas as pd
from io import BytesIO

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log
from db.client import DBClient
from api.dependencies import get_db # 雖然是獨立服務，但可以重用這個依賴項來獲取 DBClient

# --- 常數與設定 ---
log = logging.getLogger(__name__)
app = FastAPI(title="Ingestion Service")

class UrlExtractionRequest(BaseModel):
    text: str

# --- API 端點 ---
@app.post("/api/page1/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest, db: DBClient = Depends(get_db)):
    """(V7 獨立服務) 提取 URL 並使用 DBClient 儲存。"""
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    try:
        parsed_data = parse_chat_log(source_text)
        if parsed_data:
            db.add_new_urls(parsed_data, source_text)
        return parsed_data
    except Exception as e:
        log.error(f"[Ingestion Service] 處理網址提取請求時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/page1/overview_data")
async def get_overview_data(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    count_only: bool = Query(False),
    db: DBClient = Depends(get_db)
):
    """(V7 獨立服務) 使用 DBClient 獲取總覽資料。"""
    try:
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        if count_only:
            return {"count": len(results)}
        return results
    except Exception as e:
        log.error(f"[Ingestion Service] 查詢總覽資料時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="資料庫查詢失敗")

@app.get("/api/page1/export")
async def export_data(
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: DBClient = Depends(get_db)
):
    """(V7 獨立服務) 使用 DBClient 獲取資料並匯出。"""
    try:
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        df = pd.DataFrame(results)
        if 'date' in df.columns:
            df.rename(columns={'date': 'message_date'}, inplace=True)
        export_columns = ['message_date', 'author', 'url']
        df = df[export_columns]

    except Exception as e:
        log.error(f"[Ingestion Service] 匯出時讀取資料庫失敗: {e}", exc_info=True)
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
        content = f"此為 {format} 格式的預留位置匯出。\n\n篩選範圍:\n開始日期: {start_date or '未設定'}\n結束日期: {end_date or '未設定'}\n\n資料內容:\n{df.to_string()}"
        return Response(
            content=content.encode('utf-8-sig'),
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=export.{format}.txt"}
        )

@app.get("/health")
async def health_check():
    """提供一個簡單的健康檢查端點。"""
    return {"status": "ok", "service": "Ingestion Service"}

# --- 主程式啟動 (用於獨立運行) ---
if __name__ == "__main__":
    import uvicorn
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    uvicorn.run(app, host="0.0.0.0", port=8004) # 假設使用 8004 埠號
