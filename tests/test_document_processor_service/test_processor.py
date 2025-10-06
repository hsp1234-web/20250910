import pytest
import json
import httpx
from unittest.mock import AsyncMock, MagicMock

# --- 將專案根目錄加入 sys.path ---
# 這一步是必要的，以便測試腳本能找到位於 src 和 services 目錄下的模組
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 模組匯入 ---
# 從我們的服務中匯入要測試的函式
from services.document_processor_service.processor import build_analysis_prompt, analyze_text_with_llm

# --- 測試 `build_analysis_prompt` 函式 ---
def test_build_analysis_prompt_structure():
    """
    單元測試：驗證提示詞 (Prompt) 是否被正確地建構。
    """
    test_content = "這是一段測試用的文件內容。"
    prompt = build_analysis_prompt(test_content)

    # 驗證提示詞中是否包含了關鍵指令和欄位名稱
    assert "你是一位專業的金融市場分析師" in prompt
    assert "嚴格按照指定的 JSON 格式" in prompt
    assert test_content in prompt
    assert "summary" in prompt
    assert "stock_id" in prompt
    assert "strategy" in prompt
    assert "quality_score" in prompt
    assert "is_trade_related" in prompt

# --- 測試 `analyze_text_with_llm` 函式 ---

@pytest.mark.asyncio
async def test_analyze_text_with_llm_success(mocker):
    """
    單元測試：驗證在 llm_service 成功回傳有效 JSON 時，函式是否能正確解析。
    """
    # 準備一個模擬的、成功的 AI 分析結果
    mock_analysis_result = {
        "summary": "這是一段摘要",
        "stock_id": "2330",
        "strategy": "看多",
        "quality_score": 8,
        "is_trade_related": "是"
    }
    # llm_service 的回應是包含一個 response_text 鍵的 JSON
    mock_llm_response_payload = {"response_text": json.dumps(mock_analysis_result)}

    # 模擬 httpx.AsyncClient.post 的行為
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_llm_response_payload

    # 設定非同步的 post 方法
    mock_post = AsyncMock(return_value=mock_response)
    mocker.patch("httpx.AsyncClient.post", mock_post)

    # 執行被測試的函式
    result = await analyze_text_with_llm("任何測試文字")

    # 驗證結果是否與我們預期的解析結果相符
    assert result == mock_analysis_result

@pytest.mark.asyncio
async def test_analyze_text_with_llm_json_decode_error(mocker):
    """
    單元測試：驗證當 llm_service 回傳無效 JSON 時，函式是否能引發 ValueError。
    """
    # 準備一個無效的 JSON 字串
    invalid_json_string = "這不是一個有效的JSON"
    mock_llm_response_payload = {"response_text": invalid_json_string}

    # 模擬 httpx 的行為
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_llm_response_payload

    mock_post = AsyncMock(return_value=mock_response)
    mocker.patch("httpx.AsyncClient.post", mock_post)

    # 驗證在這種情況下，函式是否會如預期般引發 ValueError
    with pytest.raises(ValueError, match="llm_service 回傳的不是有效的 JSON"):
        await analyze_text_with_llm("任何測試文字")

@pytest.mark.asyncio
async def test_analyze_text_with_llm_connection_error(mocker):
    """
    單元測試：驗證當無法連線到 llm_service 時，函式是否能引發 ConnectionError。
    """
    # 模擬 httpx 在 post 時引發網路錯誤
    mocker.patch("httpx.AsyncClient.post", side_effect=httpx.RequestError("網路連線失敗"))

    # 驗證在這種情況下，函式是否會如預期般引發 ConnectionError
    with pytest.raises(ConnectionError, match="無法連線到 llm_service"):
        await analyze_text_with_llm("任何測試文字")

@pytest.mark.asyncio
async def test_analyze_text_with_llm_handles_markdown(mocker):
    """
    單元測試：驗證函式是否能正確處理被 markdown 符號包圍的 JSON。
    """
    mock_analysis_result = {"key": "value"}
    # 模擬 LLM 有時會用 markdown 區塊來包圍 JSON
    json_with_markdown = f"```json\n{json.dumps(mock_analysis_result)}\n```"
    mock_llm_response_payload = {"response_text": json_with_markdown}

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_llm_response_payload

    mock_post = AsyncMock(return_value=mock_response)
    mocker.patch("httpx.AsyncClient.post", mock_post)

    result = await analyze_text_with_llm("任何測試文字")

    # 驗證即使有 markdown 符號，結果依然能被正確解析
    assert result == mock_analysis_result