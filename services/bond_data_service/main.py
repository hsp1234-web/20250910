# services/bond_data_service/main.py

from fastapi import FastAPI

app = FastAPI(
    title="Bond Data Service",
    description="一個專門用來獲取和提供債券相關宏觀經濟數據的微服務。",
    version="0.1.0",
)

@app.get("/ping")
async def ping():
    """
    健康檢查端點，用來確認服務是否正在運行。
    """
    return {"status": "ok", "message": "Bond Data Service is running."}
