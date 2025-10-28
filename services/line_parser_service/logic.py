# services/line_parser_service/logic.py
import re
import logging
from typing import List, Dict, Optional
import sys
from pathlib import Path
import asyncio

# --- 路徑修正 ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 專案模組匯入 ---
from src.db.client import DBClient
from .line_workflow_logic import _run_line_item_processing_task, run_task_wrapper

# --- 日誌設定 ---
log = logging.getLogger(__name__)

def parse_chat_log(text: str) -> List[Dict[str, Optional[str]]]:
    """
    (Jules @ 2025-10-09) 方案 A v4: 最終修正版解析器。
    解決了無日期開頭的邊界情況，並確保上下文狀態被正確管理。
    """
    results: List[Dict[str, Optional[str]]] = []

    # 正規表示式定義
    date_pattern = re.compile(r'^\d{4}[./]\d{1,2}[./]\d{1,2}')
    # 匹配 "時間<Tab>作者" 或 "時間 作者"
    message_header_pattern = re.compile(r'^(\d{2}:\d{2})\s+(.*?)$')
    url_pattern = re.compile(r'https?://[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&/=]*)')

    # 狀態機變數
    current_date: Optional[str] = None
    last_author: Optional[str] = None
    last_time: Optional[str] = None
    potential_title: str = ""

    lines = text.split('\n')

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 1. 檢查是否為日期行
        date_match = date_pattern.match(line)
        if date_match:
            raw_date_str = date_match.group(0).split(' ')[0]
            normalized_date_str = re.sub(r'[./]', '-', raw_date_str)
            date_parts = normalized_date_str.split('-')
            current_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"
            last_author = None
            last_time = None
            potential_title = ""
            continue

        # 2. 嘗試解析 "作者<Tab>內容" 或 "時間<Tab>作者<Tab>內容"
        parts = line.split('\t')
        header_found = False

        # 檢查是否為 "時間<Tab>作者..."
        if len(parts) >= 2 and re.match(r'^\d{2}:\d{2}$', parts[0]):
            header_found = True
            last_time = parts[0]
            last_author = parts[1].strip()
            line_content = parts[2].strip() if len(parts) > 2 else ""
        # 檢查是否為 "作者<Tab>內容"
        elif len(parts) >= 2:
            # 為了避免誤判，這裡可以加入一些啟發式規則，例如作者不能包含網址
            if not url_pattern.search(parts[0]):
                 header_found = True
                 last_author = parts[0].strip()
                 last_time = None # 新作者發言，但沒有時間，重置時間
                 line_content = parts[1].strip()
            else:
                line_content = line
        else:
            line_content = line

        # 過濾系統訊息
        if header_found and last_author and (any(keyword in last_author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in line_content):
            continue

        # 3. 在當前行內容中尋找網址
        urls_found = list(url_pattern.finditer(line_content))

        if urls_found:
            if not last_author:
                continue

            last_pos = 0
            for match in urls_found:
                url = match.group(0)

                title_on_line = line_content[last_pos:match.start()].strip()
                title = title_on_line or potential_title
                title = re.sub(r'\s+', ' ', title).strip() or "無標題"

                if "提醒小作文標題格式" in title:
                    continue

                results.append({
                    'date': current_date,
                    'time': last_time,
                    'author': last_author,
                    'title': title,
                    'url': url
                })
                last_pos = match.end()

            potential_title = ""
        elif line_content:
            potential_title = line_content

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results


def save_parsed_data_to_db(parsed_data: List[Dict], source_text: str, request, background_tasks) -> List[Dict]:
    """
    [V2 改造]
    將解析後的資料存入資料庫，然後為每一個新項目啟動一個背景處理工作流。
    """
    if not parsed_data:
        log.info("沒有要儲存的資料。")
        return []

    log.info(f"準備將 {len(parsed_data)} 筆解析資料透過 DBClient 傳送至中央資料庫...")

    data_to_send = [
        {
            "url": item['url'],
            "title": item['title'],
            "author": item['author'],
            "date": item.get('date'),
            "time": item.get('time'),
            "source": "line_importer"
        }
        for item in parsed_data
    ]

    url_list = [item['url'] for item in parsed_data if item.get('url')]

    try:
        db_client = DBClient()
        inserted_count = db_client.add_new_urls(parsed_data=data_to_send, source_text=source_text)

        if inserted_count > 0:
            log.info(f"成功透過 db_manager 儲存了 {inserted_count} 筆新資料。")
            log.info(f"正在查詢剛存入的 {len(url_list)} 筆資料的詳細資訊...")
            inserted_items_details = db_client.get_urls_by_url_list(url_list)
            log.info(f"成功查詢到 {len(inserted_items_details)} 筆詳細資訊。")

            # --- [V2 改造] 觸發背景工作流 ---
            semaphore = request.app.state.processing_semaphore
            queue = request.app.state.notification_queue
            loop = asyncio.get_running_loop()

            if not semaphore or not queue:
                log.error("無法從 app.state 中獲取信號量或佇列，無法啟動背景任務。")
                return inserted_items_details # 仍然回傳已存入的項目

            log.info(f"準備為 {len(inserted_items_details)} 個新項目啟動背景處理工作流...")
            for item in inserted_items_details:
                item_id = item.get('id')
                if not item_id:
                    continue

                background_tasks.add_task(
                    run_task_wrapper,
                    task_id=item_id,
                    semaphore=semaphore,
                    blocking_func=_run_line_item_processing_task,
                    queue=queue,
                    loop=loop,
                    db_client=db_client
                )

            log.info("✅ 所有背景任務已成功加入佇列。")
            return inserted_items_details
        else:
            log.info("沒有新增任何資料（可能均為重複項）。")
            return []

    except Exception as e:
        log.error(f"呼叫 DBClient 或啟動背景任務時發生嚴重錯誤: {e}", exc_info=True)
        return []
