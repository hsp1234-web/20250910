# services/essay_ingestion_service/logic.py
import re
import logging
from typing import List, Dict
import sys
from pathlib import Path

# --- 路徑修正 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 專案模組匯入 ---
from src.db.client import DBClient

# --- 日誌設定 ---
log = logging.getLogger(__name__)

def parse_chat_log(text: str) -> List[Dict]:
    """
    (Jules @ 2025-10-09) 重構以支援多網址和更精確的標題提取。
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    """
    results = []
    current_date = None
    lines = text.split('\n')
    i = 0
    date_pattern = re.compile(r'(\d{4}[./]\d{1,2}[./]\d{1,2}).*')
    message_pattern = re.compile(r'^(\d{2}:\d{2})[\t\s]+([^\t\s].*?)[\t\s]+(.*)$')
    # 修正後的 URL 樣式，能更好地處理各種網址
    url_pattern = re.compile(r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)')

    while i < len(lines):
        line = lines[i].strip()

        # 處理日期行
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

        # 處理訊息行
        message_match = message_pattern.match(line)
        if message_match:
            time, author, first_line_content = message_match.groups()
            author = author.strip()

            # 過濾掉無關訊息，例如系統訊息或收回的訊息
            if any(keyword in author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in first_line_content:
                i += 1
                continue

            # 收集屬於同一個使用者發送的連續行
            content_lines = [first_line_content.strip()]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # 如果下一行是新的日期或新的訊息，則當前訊息塊結束
                if date_pattern.match(next_line) or message_pattern.match(next_line):
                    break
                if next_line:
                    content_lines.append(next_line)
                j += 1

            # 處理收集到的訊息塊
            potential_title = "無標題"
            for content_line in content_lines:
                url_matches = list(url_pattern.finditer(content_line))

                if url_matches:
                    # 如果該行包含 URL
                    last_pos = 0
                    for match in url_matches:
                        url = match.group(0)

                        # 標題邏輯：優先使用同一行 URL 前的文字，如果沒有，則使用上一行的內容
                        title_on_line = content_line[last_pos:match.start()].strip()
                        final_title = title_on_line or potential_title
                        final_title = re.sub(r'\s+', ' ', final_title).strip() or "無標題"

                        if "提醒小作文標題格式" in final_title:
                            continue

                        results.append({
                            'date': current_date,
                            'time': time,
                            'author': author,
                            'title': final_title,
                            'url': url
                        })
                        last_pos = match.end()

                    # 如果該行包含 URL，它本身不能作為下一行的標題
                    potential_title = "無標題"
                else:
                    # 如果該行不含 URL，則將其視為下一行的潛在標題
                    potential_title = content_line if content_line else "無標題"

            i = j # 將主迴圈的索引推進到下一個訊息塊
        else:
            i += 1

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results

def save_parsed_data_to_db(parsed_data: List[Dict], source_text: str) -> List[Dict]:
    """
    [V4] 將解析後的資料存入資料庫，並查詢存入的詳細資訊後回傳。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return []

    log.info(f"準備將 {len(parsed_data)} 筆解析資料透過 DBClient 傳送至中央資料庫...")

    # 準備要寫入的資料
    data_to_send = [
        {
            "url": item['url'],
            "title": item['title'],
            "author": item['author'],
            "date": item['date'],
            "time": item['time'],
            "source": "essay_performance"
        }
        for item in parsed_data
    ]

    # 提取所有 URL，以便後續查詢
    url_list = [item['url'] for item in parsed_data]

    try:
        db_client = DBClient()
        inserted_count = db_client.add_new_urls(parsed_data=data_to_send, source_text=source_text)

        if inserted_count > 0:
            log.info(f"成功透過 db_manager 儲存了 {inserted_count} 筆新資料。")
            # 儲存後，立即查詢這些資料的詳細資訊
            log.info(f"正在查詢剛存入的 {len(url_list)} 筆資料的詳細資訊...")
            inserted_items_details = db_client.get_urls_by_url_list(url_list)
            log.info(f"成功查詢到 {len(inserted_items_details)} 筆詳細資訊。")
            return inserted_items_details
        else:
            log.info("沒有新增任何資料（可能均為重複項）。")
            return []

    except Exception as e:
        log.error(f"呼叫 DBClient 時發生嚴重錯誤: {e}", exc_info=True)
        return []