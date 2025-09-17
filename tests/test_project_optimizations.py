# 專為本次優化任務建立的測試檔案
# 測試案例將在此檔案中陸續添加
import pytest
from src.db.database import get_urls_by_statuses, add_new_urls, get_db_connection

def test_get_urls_does_not_fetch_source_text(db_conn):
    """
    驗證 get_urls_by_statuses 函數在查詢時不會獲取龐大的 source_text 欄位。
    這個測試在優化前應該會失敗。
    """
    # 步驟 1: 準備測試資料
    # 構造一個符合 add_new_urls 函數期望的資料列表
    test_entry = {
        "url": "https://example.com/test-entry",
        "author": "Test Author",
        "date": "2025-09-17",
        "time": "12:00",
        "title": "Initial Test Title"
    }
    long_source_text = "This is a very long and verbose source text that should not be fetched in a summary list."

    # add_new_urls 內部會自行取得連線，而測試環境已透過 conftest 設定好
    # 它會自動將資料狀態設為 'pending'
    add_new_urls([test_entry], long_source_text)

    # 步驟 2: 執行被測試的函數
    # get_urls_by_statuses 也會自行取得連線
    results = get_urls_by_statuses(statuses=["pending"])

    # 步驟 3: 斷言結果
    assert len(results) == 1, "資料庫中應只有一筆 'pending' 狀態的資料"

    result_item = results[0]

    # 核心斷言：確認 'source_text' 不在回傳的欄位中
    # sqlite3.Row 物件可以像字典一樣用 .keys() 方法
    assert 'source_text' not in result_item.keys(), "優化後的查詢結果不應包含 'source_text' 欄位"

    # 輔助斷言：確認必要的欄位仍然存在
    assert 'id' in result_item.keys()
    assert 'url' in result_item.keys()
    assert 'title' in result_item.keys()
    assert result_item['url'] == "https://example.com/test-entry"
    assert result_item['author'] == "Test Author"


from src.tools.url_extractor import parse_chat_log, save_urls_to_db

def test_url_extraction_generates_correct_title(db_conn):
    """
    驗證從解析到儲存的完整流程能正確處理標題。
    - `parse_chat_log` 應正確提取標題。
    - `save_urls_to_db` 應正確將標題存入資料庫。
    此測試在修正儲存邏輯前應該會失敗。
    """
    # 步驟 1: 準備輸入文字
    chat_text = "2025/09/17（週三）\n10:30\tJules\t這是一個重要的標題 https://example.com/important-link"

    # 步驟 2: 執行解析和儲存
    # 2a: 解析聊天記錄
    parsed_data = parse_chat_log(chat_text)
    assert len(parsed_data) == 1
    # 先驗證解析器本身是正常的
    assert parsed_data[0]['title'] == "這是一個重要的標題"

    # 2b: 儲存到資料庫 (我們傳入 db_conn fixture 以使用測試資料庫)
    save_urls_to_db(parsed_data, chat_text, conn=db_conn)

    # 步驟 3: 從資料庫取回資料並驗證
    cursor = db_conn.cursor()
    cursor.execute("SELECT id, title FROM extracted_urls WHERE url = ?", ("https://example.com/important-link",))
    saved_item = cursor.fetchone()

    assert saved_item is not None, "資料應該已被存入資料庫"
    # 核心斷言：資料庫中的標題應與解析出的標題相符
    # 預期會失敗，因為舊的 save_urls_to_db 沒有儲存 title
    assert saved_item['title'] == "這是一個重要的標題", f"資料庫中的標題為 '{saved_item['title']}'，與預期的 '這是一個重要的標題' 不符"
