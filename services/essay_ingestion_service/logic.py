# services/essay_ingestion_service/logic.py
import re
import logging
from typing import List, Dict

# --- 專案模組匯入 ---
# 重構為使用中央資料庫客戶端，而非直接連接
from src.db.client import DBClient

# --- 日誌設定 ---
log = logging.getLogger(__name__)

def parse_chat_log(text: str) -> List[Dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    (Jules: 此函式邏輯不變，因為它與資料庫無關)
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
    [重構後版本] 將解析後的資料透過 DBClient 傳送給 db_manager 服務進行儲存。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return []

    log.info(f"準備將 {len(parsed_data)} 筆解析資料透過 DBClient 傳送至中央資料庫...")

    # 將解析結果轉換為 db_manager `add_urls` action 期望的格式
    data_to_send = [
        {
            "url": item['url'],
            "title": item['title'],
            "author": item['author'],
            "message_date": item['date'],
            "message_time": item['time'],
            "source": "essay_performance" # 標記資料來源
        }
        for item in parsed_data
    ]

    try:
        db_client = DBClient()
        # 呼叫中央資料庫服務，'add_urls' action 會處理重複資料的過濾
        response_data = db_client.add_urls(urls_data=data_to_send)

        if response_data and response_data.get('status') == 'success':
            inserted_items = response_data.get('data', [])
            log.info(f"成功透過 db_manager 儲存了 {len(inserted_items)} 筆新資料。")
            # 回傳的資料應已包含 ID
            return inserted_items
        else:
            error_msg = response_data.get('message', '未知的 db_manager 錯誤')
            log.error(f"透過 db_manager 儲存資料失敗: {error_msg}")
            return []

    except Exception as e:
        log.error(f"呼叫 DBClient 時發生嚴重錯誤: {e}", exc_info=True)
        return []