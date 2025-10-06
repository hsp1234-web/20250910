import pytest
import json
import httpx
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, ANY

# --- 將專案根目錄加入 sys.path ---
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 模組匯入 ---
from services.document_processor_service.processor import build_analysis_prompt, analyze_text_with_llm, process_document_url
from services.document_processor_service.stock_id_extractor import extract_stock_ids

# --- 測試 `build_analysis_prompt` 函式 (已更新) ---

def test_build_analysis_prompt_with_stock_ids():
    """
    單元測試：驗證當提供股票代號時，提示詞是否被正確建構。
    """
    test_content = "這是一段關於 3711 的文件內容。"
    stock_ids = ["3711"]
    prompt = build_analysis_prompt(test_content, stock_ids)

    assert "你是一位專業、謹慎的金融市場分析師" in prompt
    assert "預提取的股票代號" in prompt
    assert f"識別出以下台股股票代號：{stock_ids}" in prompt
    assert test_content in prompt
    assert "analyzed_stock_ids" in prompt
    # 舊的 "stock_id": (字串) 格式不應存在，這個斷言更精確，避免被 'analyzed_stock_ids' 誤判
    assert '"stock_id":' not in prompt

def test_build_analysis_prompt_without_stock_ids():
    """
    單元測試：驗證當未提供股票代號時，提示詞是否也能被正確建構。
    """
    test_content = "這是一段沒有代號的文件內容。"
    stock_ids = []
    prompt = build_analysis_prompt(test_content, stock_ids)

    assert "沒有找到任何台股股票代號" in prompt
    assert "analyzed_stock_ids" in prompt

# --- 測試 `analyze_text_with_llm` 函式 (已更新) ---

@pytest.mark.asyncio
async def test_analyze_text_with_llm_success(mocker):
    """
    單元測試：驗證在 llm_service 成功回傳有效 JSON 時，函式是否能正確解析。
    """
    mock_analysis_result = {
        "summary": "這是一段摘要",
        "analyzed_stock_ids": ["2330"],
        "strategy": "看多",
        "quality_score": 8,
        "is_trade_related": "是"
    }
    mock_llm_response_payload = {"response_text": json.dumps(mock_analysis_result)}

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = mock_llm_response_payload

    mock_post = AsyncMock(return_value=mock_response)
    mocker.patch("httpx.AsyncClient.post", mock_post)

    result = await analyze_text_with_llm("任何測試文字", stock_ids=["2330"])
    assert result == mock_analysis_result

# --- 新增的整合測試 (已修正) ---

# 從 plan14_poc.md 複製的真實測試文本
REAL_TEST_TEXT = """
小作文 日月光投控 3711 公司簡介 隸屬 電子–半導體 產業類別。資本額 441.53 億 日月光投資控股股份有限公司（以下稱本公司）於107 年4 月30 日設立於高雄楠梓科技 產業園區。所營業務主要為半導體、基板、電腦週邊設備及電子零配件之製造、組合、加 工、測試及銷售。 觀看角度 基本面：毛利率連續 4 季較去年同期成長。本益比為過去五年平均高點 技術面：受大盤影響已連續三個跳空下跌 籌碼面：大戶持股比例高 投信連買一個月 外資持續賣超 消息面：投入66 億投資新廠，設立面板及扇出型封裝產線，預計第二季設備進廠 第三季 試量產，送樣客戶驗證。 扇出型封裝特色：顯著降低成本、解決散熱訊號串接問題、解決客戶現有12 吋晶圓尺寸 不夠用問題 個人觀點 先進封裝需求不減，新型封裝方式成本降低同時吸引更多訂單，未來獲利可期 已長遠角度觀察現在價格位階並不高，加上投信連續買進，待外資賣壓減弱後可望止穩， 靜待大盤回覆正常盤勢，可望跟隨大盤一同起漲。
"""

@pytest.mark.asyncio
async def test_process_document_url_integration_with_real_text(mocker):
    """
    整合測試：使用真實文本，驗證從「下載」到「儲存」的完整串聯流程。
    這個測試會真實執行 `extract_stock_ids`，但會模擬所有 I/O 和外部服務。
    """
    # --- 1. 設定 (Arrange) ---
    test_url = "http://example.com/real_report.pdf"
    fake_path = "/fake/path/real_report.pdf"

    mock_ai_response = {
        "summary": "AI 對日月光投控的分析摘要。",
        "analyzed_stock_ids": ["3711"],
        "strategy": "看多",
        "quality_score": 9,
        "is_trade_related": "是"
    }

    # 模擬所有同步 I/O 函式
    mock_update_status = mocker.patch('services.document_processor_service.processor.update_task_status')
    mocker.patch('services.document_processor_service.processor.download_file', return_value=(True, fake_path, "Success"))
    mocker.patch('services.document_processor_service.processor.extract_content', return_value={"text": REAL_TEST_TEXT, "images": []})
    mock_save_analysis = mocker.patch('services.document_processor_service.processor.save_successful_analysis')
    mock_os_path_exists = mocker.patch('services.document_processor_service.processor.os.path.exists', return_value=True)
    mock_os_remove = mocker.patch('services.document_processor_service.processor.os.remove')

    # 模擬非同步的 analyze_text_with_llm
    mock_analyze_llm = mocker.patch('services.document_processor_service.processor.analyze_text_with_llm', new_callable=AsyncMock, return_value=mock_ai_response)

    # 關鍵修正：建立一個 async def 的 mock 來正確模擬 asyncio.to_thread
    # 這樣它回傳的就是一個協程 (coroutine)，可以被 `await`
    async def sync_to_thread_mock(func, *args, **kwargs):
        # 直接同步執行被傳入的函式，並回傳其結果
        return func(*args, **kwargs)
    mocker.patch('services.document_processor_service.processor.asyncio.to_thread', new=sync_to_thread_mock)

    # --- 2. 執行 (Act) ---
    await process_document_url(test_url)

    # --- 3. 斷言 (Assert) ---
    mock_update_status.assert_any_call(test_url, 'processing')

    # 驗證 `analyze_text_with_llm` 的呼叫
    mock_analyze_llm.assert_called_once_with(REAL_TEST_TEXT, ["3711"])

    # 驗證儲存函式
    mock_save_analysis.assert_called_once_with(test_url, mock_ai_response)

    # 驗證沒有呼叫失敗狀態
    for call in mock_update_status.call_args_list:
        assert call.args[1] != 'failed'

    # 驗證檔案清理
    mock_os_path_exists.assert_called_once_with(fake_path)
    mock_os_remove.assert_called_once_with(fake_path)