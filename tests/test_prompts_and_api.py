# tests/test_prompts_and_api.py

import sys
from pathlib import Path
from fastapi.testclient import TestClient

# 將專案的 src 目錄新增到 Python 的搜尋路徑中
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# 從主應用程式匯入 FastAPI 實例
from api.api_server import app

# 建立一個測試客戶端
client = TestClient(app)

def test_gemini_processor_loads_html_prompt():
    """
    驗證 `gemini_processor` 工具是否能成功載入 `format_as_html` 提示詞。
    這是對計畫第一步修復的直接驗證。
    """
    # 延遲匯入，以確保 sys.path 已被修改
    from tools.gemini_processor import ALL_PROMPTS

    assert "format_as_html" in ALL_PROMPTS
    assert isinstance(ALL_PROMPTS["format_as_html"], str)
    assert "{video_title_for_html}" in ALL_PROMPTS["format_as_html"]

def test_prompt_api_routes():
    """
    驗證提示詞 API 的路由是否正確。
    - 正確的路由 /api/prompts 應該回傳 200 OK。
    - 錯誤的路由 /api/analyzer/prompts 應該回傳 404 Not Found。
    這是對計畫第二步修復的直接驗證。
    """
    # 測試正確的路由
    response_correct = client.get("/api/prompts")
    assert response_correct.status_code == 200

    # 驗證回傳的 JSON 內容是否符合預期
    data = response_correct.json()
    assert "stage_1_extraction_prompt" in data
    assert "format_as_html" in data # 確保新加入的提示詞也透過 API 回傳

    # 測試錯誤的（舊的）路由
    response_incorrect = client.get("/api/analyzer/prompts")
    assert response_incorrect.status_code == 404