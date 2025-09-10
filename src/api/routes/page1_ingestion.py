import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

# --- 路徑修正與模組匯入 ---
# 這是必要的，因為我們的工具和資料庫模組都在 src 下
# 我們需要確保 src 目錄在 Python 的搜尋路徑中
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# 現在可以安全地匯入我們的工具了
from tools.url_extractor import extract_urls, save_urls_to_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# --- Pydantic 模型 ---
class UrlExtractionRequest(BaseModel):
    text: str

# --- API 端點 (重構後) ---
@router.post("/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest):
    """
    接收文字，提取其中的網址，並將其存入資料庫。
    (此版本經過重構，直接呼叫工具函式，而非使用 subprocess)
    """
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    log.info(f"API: 收到提取網址的請求，文字長度: {len(source_text)}")

    try:
        # 步驟 1: 直接呼叫函式來提取網址
        urls_found = extract_urls(source_text)
        count = len(urls_found)

        # 步驟 2: 如果找到網址，直接呼叫函式將其儲存到資料庫
        if urls_found:
            save_urls_to_db(urls_found, source_text)
        else:
            log.info("API: 在提供的文字中未找到任何網址。")

        return JSONResponse(
            content={
                "message": "網址提取與儲存成功。",
                "urls_found_count": count
            }
        )
    except Exception as e:
        log.error(f"API: 處理網址提取請求時發生未預期錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器發生內部錯誤: {e}")


@router.get("/api/search_urls")
async def search_urls_endpoint(q: str = ""):
    """
    從資料庫中搜尋符合關鍵字的網址。
    """
    if not q.strip():
        return JSONResponse(content=[])

    log.info(f"API: 收到網址搜尋請求，關鍵字: '{q}'")
    conn = None
    try:
        # 從 db 模組獲取資料庫連線
        from db.database import get_db_connection
        conn = get_db_connection()
        cursor = conn.cursor()
        # 使用 LIKE 進行簡單的子字串搜尋
        cursor.execute("SELECT id, url, created_at FROM extracted_urls WHERE url LIKE ?", (f"%{q}%",))
        rows = cursor.fetchall()
        # 將查詢結果轉換為字典列表以便序列化為 JSON
        results = [{"id": row[0], "url": row[1], "created_at": row[2]} for row in rows]
        log.info(f"API: 搜尋到 {len(results)} 筆結果。")
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 搜尋網址時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="搜尋網址時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
