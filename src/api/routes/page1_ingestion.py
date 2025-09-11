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
from tools.url_extractor import parse_chat_log, save_urls_to_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

# --- Pydantic 模型 ---
class UrlExtractionRequest(BaseModel):
    text: str

# --- API 端點 (重構後) ---
@router.post("/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest, request: Request):
    """
    [新版] 接收文字，使用新的解析器解析，並回傳結構化資料。
    """
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    log.info(f"API: 收到解析聊天紀錄的請求，文字長度: {len(source_text)}")

    try:
        # 步驟 1: 呼叫新的解析器
        parsed_data = parse_chat_log(source_text)
        count = len(parsed_data)

        # [步驟四完成] - 重新啟用儲存功能
        if parsed_data:
            # 現在 save_urls_to_db 已更新，可以處理新的結構
            save_urls_to_db(parsed_data, source_text)
            log.info(f"API: 成功解析並儲存 {count} 筆資料，正在廣播通知...")
            # 廣播 WebSocket 訊息 (如果需要)
            await request.app.state.manager.broadcast_json({
                "type": "URLS_EXTRACTED",
                "payload": {"count": count}
            })
        else:
            log.info("API: 在提供的文字中未找到任何可解析的資料。")

        # 步驟 2: 直接回傳解析後的結構化資料列表給前端
        return JSONResponse(content=parsed_data)

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
