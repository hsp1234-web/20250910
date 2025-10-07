# services/essay_ingestion_service/main.py
import uvicorn
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
import logging

# 從本地模組匯入核心邏輯
try:
    from logic import parse_chat_log, save_parsed_data_to_db
except ImportError:
    # 為了讓 Python 能夠找到 logic 模組，我們需要將當前目錄加入到 sys.path
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    from logic import parse_chat_log, save_parsed_data_to_db


# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service_main')

# --- FastAPI 應用實例 ---
app = FastAPI(
    title="小作文擷取服務 (Essay Ingestion Service)",
    description="一個獨立的微服務，專門用於解析 LINE 聊天紀錄並將其儲存至資料庫。",
    version="1.0.0"
)

# --- 資料模型 (Pydantic Model) ---
class IngestRequest(BaseModel):
    text: str

class IngestResponse(BaseModel):
    message: str
    inserted_count: int

# --- API 端點 ---
@app.post("/ingest", response_model=IngestResponse)
async def ingest_text(request: IngestRequest):
    """
    接收文字，解析後存入資料庫。
    """
    log.info("接收到 /ingest 請求。")
    if not request.text or not request.text.strip():
        log.warning("請求的文字內容為空。")
        raise HTTPException(status_code=400, detail="文字內容不可為空。")

    try:
        # 步驟 1: 解析聊天紀錄
        log.info("開始解析文字...")
        parsed_data = parse_chat_log(request.text)
        if not parsed_data:
            log.info("從文字中未解析出任何有效資料。")
            return IngestResponse(message="未解析出有效資料。", inserted_count=0)

        # 步驟 2: 儲存到資料庫
        log.info(f"解析出 {len(parsed_data)} 筆資料，準備存入資料庫...")
        inserted_count = save_parsed_data_to_db(parsed_data)
        log.info(f"成功儲存 {inserted_count} 筆新資料。")

        return IngestResponse(
            message=f"處理完成，成功新增 {inserted_count} 筆資料。",
            inserted_count=inserted_count
        )

    except Exception as e:
        log.error(f"處理 /ingest 請求時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"內部伺服器錯誤: {e}")

# --- 啟動配置 ---
if __name__ == "__main__":
    log.info("準備以獨立模式啟動「小作文擷取服務」...")
    # 注意：在生產環境中，協調器 (orchestrator) 會以程式化方式啟動此服務。
    # 此處的 uvicorn.run 主要用於獨立開發和測試。
    uvicorn.run(app, host="0.0.0.0", port=8001)