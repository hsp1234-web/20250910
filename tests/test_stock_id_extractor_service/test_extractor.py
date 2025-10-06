import pytest
from unittest.mock import patch

# --- 將專案根目錄加入 sys.path ---
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 模組匯入 ---
from services.stock_id_extractor_service.extractor import extract_stock_ids

# --- 模擬的股票代號列表 ---
# 我們定義一個固定的、模擬的股票代號集合，以便在測試中使用
MOCK_STOCK_CODES = {'2330', '3711', '0050', '2882'}

# --- Pytest 測試案例 ---

@patch('services.stock_id_extractor_service.extractor.get_all_stock_codes', return_value=MOCK_STOCK_CODES)
def test_extract_mixed_ids(mock_get_codes):
    """
    測試案例 1：正常情況，包含有效、無效及重複的代號。
    """
    test_text = "這是台積電 2330 的分析，以及日月光 3711 的報告。還有一個假的代號 9999，並重複一次台積電 2330。"
    expected_result = ['2330', '3711']
    assert extract_stock_ids(test_text) == expected_result

@patch('services.stock_id_extractor_service.extractor.get_all_stock_codes', return_value=MOCK_STOCK_CODES)
def test_extract_no_ids(mock_get_codes):
    """
    測試案例 2：文本中完全不包含任何四位數字。
    """
    test_text = "這是一段完全沒有股票代號的分析報告。"
    expected_result = []
    assert extract_stock_ids(test_text) == expected_result

@patch('services.stock_id_extractor_service.extractor.get_all_stock_codes', return_value=MOCK_STOCK_CODES)
def test_extract_empty_string(mock_get_codes):
    """
    測試案例 3：輸入為空字串。
    """
    test_text = ""
    expected_result = []
    assert extract_stock_ids(test_text) == expected_result

@patch('services.stock_id_extractor_service.extractor.get_all_stock_codes', return_value=MOCK_STOCK_CODES)
def test_extract_with_boundary_conditions(mock_get_codes):
    """
    測試案例 4：邊界情況，包含看起來像代號但格式不符的數字。
    """
    test_text = "這是一個五位數 12345，一個三位數 123，還有一個被字母包圍的 A2882B。只有 0050 是有效的。"
    expected_result = ['0050']
    assert extract_stock_ids(test_text) == expected_result

@patch('services.stock_id_extractor_service.extractor.get_all_stock_codes', return_value=MOCK_STOCK_CODES)
def test_extract_only_invalid_ids(mock_get_codes):
    """
    測試案例 5：文本中只包含無效的四位數字代號。
    """
    test_text = "這裡有兩個無效的代號：1111 和 2222。"
    expected_result = []
    assert extract_stock_ids(test_text) == expected_result