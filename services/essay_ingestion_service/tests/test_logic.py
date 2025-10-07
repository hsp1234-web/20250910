# services/essay_ingestion_service/tests/test_logic.py
import pytest
import sys
from pathlib import Path

# --- 路徑設定 ---
# 將微服務的根目錄加入到 sys.path，以便 pytest 可以找到 logic 模組
SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from logic import parse_chat_log

# --- 測試資料 ---
SAMPLE_CHAT_LOG = """
2025/10/07(週二)
15:00	作者A	這是一個標題 https://example.com/page1
這是訊息的第二行
15:05	作者B	這是另一個標題
https://example.com/page2
15:10	系統訊息	作者C已加入聊天。
15:12	作者A	這是一個沒有標題的連結 https://example.com/page3
2025.10.08(週三)
09:00	作者D	一個跨日的標題 https://example.com/page4
"""

EXPECTED_RESULTS = [
    {
        'date': '2025-10-07',
        'time': '15:00',
        'author': '作者A',
        'title': '這是一個標題',
        'url': 'https://example.com/page1'
    },
    {
        'date': '2025-10-07',
        'time': '15:05',
        'author': '作者B',
        'title': '這是另一個標題',
        'url': 'https://example.com/page2'
    },
    {
        'date': '2025-10-07',
        'time': '15:12',
        'author': '作者A',
        'title': '這是一個沒有標題的連結',
        'url': 'https://example.com/page3'
    },
    {
        'date': '2025-10-08',
        'time': '09:00',
        'author': '作者D',
        'title': '一個跨日的標題',
        'url': 'https://example.com/page4'
    }
]

# --- 測試案例 ---
def test_parse_chat_log_successfully():
    """
    測試 parse_chat_log 函式是否能正確解析一個標準的聊天紀錄。
    """
    # 執行解析
    results = parse_chat_log(SAMPLE_CHAT_LOG)

    # 驗證結果數量
    assert len(results) == len(EXPECTED_RESULTS), "解析出的項目數量不符合預期"

    # 逐一驗證每個解析出的項目
    for i, expected in enumerate(EXPECTED_RESULTS):
        assert results[i]['date'] == expected['date'], f"第 {i} 項的日期不符"
        assert results[i]['time'] == expected['time'], f"第 {i} 項的時間不符"
        assert results[i]['author'] == expected['author'], f"第 {i} 項的作者不符"
        assert results[i]['title'] == expected['title'], f"第 {i} 項的標題不符"
        assert results[i]['url'] == expected['url'], f"第 {i} 項的 URL 不符"

def test_parse_chat_log_with_empty_string():
    """
    測試當輸入為空字串時，解析器是否能正常處理並返回空列表。
    """
    results = parse_chat_log("")
    assert results == [], "輸入為空字串時，應返回空列表"

def test_parse_chat_log_with_no_urls():
    """
    測試當聊天紀錄中不包含任何 URL 時，解析器是否返回空列表。
    """
    log_without_urls = """
    2025/10/07(週二)
    15:00	作者A	這是一條沒有網址的訊息。
    15:05	作者B	我也是。
    """
    results = parse_chat_log(log_without_urls)
    assert results == [], "沒有 URL 的紀錄應返回空列表"