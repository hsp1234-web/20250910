# services/llm_service/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel

# 從我們的模組導入模型管理器
from model_manager import ModelManager

# --- 全域變數 ---
# 這個變數將在服務啟動時被賦值
model_manager: ModelManager | None = None

# --- Pydantic 模型定義 ---
# 用於定義請求和回應的資料結構，提供自動的資料驗證
class GenerateRequest(BaseModel):
    model: str = "qwen2:1.5b"  # 設置預設模型
    prompt: str

class GenerateResponse(BaseModel):
    model: str
    response_text: str

class ModelInfo(BaseModel):
    name: str
    modified_at: str
    size: int

# --- 非同步生命週期管理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    在服務啟動和關閉時執行的非同步上下文管理器。
    """
    global model_manager
    # 在應用啟動時執行的程式碼
    print("LLM Service is starting up...")
    # 建立 ModelManager 的實例，它會嘗試連接到 Ollama
    model_manager = ModelManager()

    yield

    # 在應用關閉時執行的程式碼
    print("LLM Service is shutting down...")
    model_manager = None

# --- FastAPI 應用程式實例 ---
app = FastAPI(
    lifespan=lifespan,
    title="LLM Service",
    description="一個用於與本地大型語言模型互動的微服務，支援懶加載。",
    version="0.1.0",
)

# --- CORS (跨來源資源共用) 設定 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- API 端點 ---
@app.get("/ping")
async def ping():
    """
    一個簡單的健康檢查端點。
    """
    return {"status": "ok", "message": "LLM Service is running."}

@app.get("/models", response_model=list[ModelInfo])
async def list_models():
    """
    列出本地 Ollama 環境中所有可用的模型。
    """
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager 未初始化。")

    try:
        models = model_manager.list_local_models()
        if "error" in models:
             raise HTTPException(status_code=500, detail=models["error"])
        return models
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"獲取模型列表時發生錯誤: {e}")


@app.post("/generate", response_model=GenerateResponse)
async def generate_text_endpoint(request: GenerateRequest):
    """
    接收一個提示詞和模型名稱，生成並返回文字結果。
    如果指定的模型不在本地，會自動觸發下載。
    """
    if not model_manager:
        raise HTTPException(status_code=503, detail="ModelManager 未初始化。")

    try:
        # 呼叫模型管理器的生成功能
        response_text = await model_manager.generate_text(
            model_name=request.model,
            prompt=request.prompt
        )

        # 返回一個結構化的回應
        return GenerateResponse(
            model=request.model,
            response_text=response_text
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e)) # 503 Service Unavailable
    except IOError as e:
        raise HTTPException(status_code=500, detail=str(e)) # 模型下載失敗
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) # 模型推論失敗
    except Exception as e:
        # 捕捉所有其他未預期的錯誤
        raise HTTPException(status_code=500, detail=f"處理請求時發生未預期錯誤: {e}")