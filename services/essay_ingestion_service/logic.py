# services/essay_ingestion_service/logic.py
import re
import sys
from pathlib import Path
import logging
from typing import List, Dict

# --- 專案根目錄設定，確保可以正確 import src ---
# 走訪三層目錄回到專案根目錄 (services/essay_ingestion_service -> services -> project_root)
# 這樣才能夠找到 src 目錄
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from src.db.client import DBClient

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger('essay_ingestion_service')

# (Jules @ 2025-10-08) 移除 initialize_database 和 get_db_connection
# 此服務不應再直接操作資料庫，所有操作都應透過 DBClient 代理

def parse_chat_log(text: str) -> List[Dict]:
    """
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
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

def save_parsed_data_to_db(parsed_data: List[Dict], source_text: str) -> List[Dict]:
    """
    [重構後] 將解析後的資料透過 DBClient 傳送給 db_manager 服務進行儲存。
    這個函式現在負責與微服務架構整合，而不是直接操作資料庫。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return []

    try:
        log.info("初始化 DBClient，準備將資料傳送至 db_manager...")
        db_client = DBClient()

        # 組合 message_date
        for item in parsed_data:
            item['message_date'] = f"{item['date']} {item['time']}"

        log.info(f"正在呼叫 db_client.add_new_urls，準備新增 {len(parsed_data)} 筆資料...")

        # 呼叫 DBClient 的方法，將資料傳送給 db_manager
        # db_manager 內部會處理去重和儲存邏輯
        # 傳遞 source_text 可讓 db_manager 根據雜湊值判斷來源文字是否重複處理
        newly_added_rows = db_client.add_new_urls(
            parsed_data=parsed_data,
            source_text=source_text
        )

        if newly_added_rows:
            log.info(f"成功透過 db_manager 新增了 {len(newly_added_rows)} 筆資料。")
            # add_new_urls 預期會回傳新增的項目列表，包含 ID
            return newly_added_rows
        else:
            log.info("db_manager 回報沒有新增任何資料 (可能都已存在)。")
            return []

    except Exception as e:
        log.error(f"透過 DBClient 儲存資料時發生嚴重錯誤: {e}", exc_info=True)
        # 在生產環境中，這裡可能需要更複雜的錯誤處理或重試機制
        return []