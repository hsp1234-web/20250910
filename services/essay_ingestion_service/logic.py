# services/essay_ingestion_service/logic.py
import re
import logging
from typing import List, Dict

# 引入中央資料庫客戶端
from src.db.client import DBClient

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service')


# 由於此服務不再直接操作資料庫，
# initialize_database, get_db_connection, _add_column_if_not_exists
# 以及所有 sqlite3 相關的程式碼都已被移除。
# 資料庫操作現由 db_manager 服務統一處理。


def parse_chat_log(text: str) -> List[Dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    (此函式邏輯不變)
    """
    results = []
    current_date = None
    lines = text.split('\n')
    i = 0
    date_pattern = re.compile(r'(\d{4}[./]\d{1,2}[./]\d{1,2}).*')
    message_pattern = re.compile(r'^(\d{2}:\d{2})[\t\s]+([^\t\s].*?)[\t\s]+(.*)$')
    url_pattern = re.compile(r'https?://\S+')
    while i < len(lines):
        line = lines[i].strip()
        date_match = date_pattern.match(line)
        if date_match:
            raw_date_str = date_match.group(1)
            normalized_date_str = re.sub(r'[./]', '-', raw_date_str)
            date_parts = normalized_date_str.split('-')
            current_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"
            i += 1
            continue
        if not current_date:
            i += 1
            continue
        message_match = message_pattern.match(line)
        if message_match:
            time, author, first_line_content = message_match.groups()
            author = author.strip()
            if any(keyword in author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in first_line_content:
                i += 1
                continue
            content_parts = [first_line_content.strip()]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                if date_pattern.match(next_line) or message_pattern.match(next_line):
                    break
                if next_line:
                    content_parts.append(next_line)
                j += 1
            full_content_str = " ".join(content_parts)
            url_match = url_pattern.search(full_content_str)
            if url_match:
                url = url_match.group(0)
                title_raw = full_content_str[:url_match.start()]
                title = re.sub(r'\s+', ' ', title_raw).strip() or "無標題"
                if "提醒小作文標題格式" in title:
                    i = j
                    continue
                results.append({'date': current_date, 'time': time, 'author': author, 'title': title, 'url': url})
            i = j
        else:
            i += 1
    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results

def save_parsed_data_to_db(parsed_data: List[Dict]) -> List[Dict]:
    """
    [重構版本] 將解析後的資料透過 db_manager 服務儲存到中央資料庫。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return []

    # 準備要傳送給 db_manager 的資料結構
    data_for_db_manager = [
        {
            'url': item['url'],
            'title': item['title'],
            'author': item['author'],
            'message_date': f"{item['date']} {item['time']}",
            'source': 'essay_performance' # 標記資料來源
        }
        for item in parsed_data
    ]

    log.info(f"準備將 {len(data_for_db_manager)} 筆資料傳送至 db_manager 服務進行儲存...")

    try:
        db_client = DBClient()
        # 呼叫 db_manager 的 'add_new_urls' 動作
        # db_manager 內部會處理重複網址的過濾
        result = db_client.call('add_new_urls', data=data_for_db_manager)

        if result and result.get('status') == 'success':
            newly_added_items = result.get('data', [])
            if newly_added_items:
                log.info(f"成功透過 db_manager 儲存了 {len(newly_added_items)} 筆新資料。")
            else:
                log.info("db_manager 確認所有網址皆已存在，未新增資料。")
            # 回傳包含新 ID 的項目列表 (可能為空)
            return newly_added_items
        else:
            error_message = result.get('message', '未知的錯誤') if result else '服務未回傳有效訊息'
            log.error(f"透過 db_manager 儲存資料失敗: {error_message}")
            return []

    except Exception as e:
        log.error(f"呼叫 db_manager 服務時發生嚴重錯誤: {e}", exc_info=True)
        return []