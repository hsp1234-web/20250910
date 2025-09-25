# src/tools/url_extractor.py
"""
這是一個命令列工具，用於從一段給定的文字中提取所有網址，
並將這些網址儲存到應用程式的 SQLite 資料庫中。

主要功能：
- 使用正規表示式從文字中尋找 http/https 網址。
- 連線到資料庫並將提取到的網址寫入 `extracted_urls` 資料表。
- 可作為獨立腳本透過命令列執行。
"""

import re
import argparse
import sys
from pathlib import Path
import logging
from typing import Optional

# --- 路徑修正 (已在 main.py 中處理) ---

# --- 本地匯入 ---
# 這些模組現在應該能被 core_service 的主應用程式找到
from core.time_utils import get_current_taipei_time_iso

# --- 日誌設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger('url_extractor')

def parse_chat_log(text: str) -> list[dict]:
    """
    (Jules @ 2025-09-17) 新版解析器
    從給定的 LINE 聊天紀錄文字中，解析出日期、時間、作者、標題和連結。
    這個實作採用區塊化處理，能夠正確處理跨多行的訊息。

    :param text: 包含 LINE 聊天紀錄的來源文字。
    :return: 一個字典列表，每個字典包含 'date', 'time', 'author', 'title', 'url'。
    """
    results = []
    current_date = None
    lines = text.split('\n')
    i = 0

    # 定義正規表示式
    # 恢復為更精確的日期格式，此格式在第二次檢查時被證實是正確的
    date_pattern = re.compile(r'(\d{4}/\d{1,2}/\d{1,2})（週.）')
    message_pattern = re.compile(r'^(\d{2}:\d{2})\t([^\t]+)\t?(.*)$')
    url_pattern = re.compile(r'https?://\S+')

    while i < len(lines):
        line = lines[i].strip()
        log.debug(f"正在處理第 {i} 行: '{line[:50]}...'")

        # 1. 處理日期行
        date_match = date_pattern.match(line)
        if date_match:
            # 將 YYYY/M/D 格式標準化為 YYYY-MM-DD
            date_parts = date_match.group(1).split('/')
            current_date = f"{date_parts[0]}-{int(date_parts[1]):02d}-{int(date_parts[2]):02d}"
            i += 1
            continue

        if not current_date:
            i += 1
            continue

        # 2. 處理訊息行
        message_match = message_pattern.match(line)
        if message_match:
            time, author, first_line_content = message_match.groups()
            author = author.strip()

            # 過濾系統訊息
            if any(keyword in author for keyword in ["加入聊天", "退出聊天"]) or "已收回訊息" in first_line_content:
                i += 1
                continue

            # 收集完整的訊息區塊 (包含後續行)
            content_parts = [first_line_content.strip()]
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                # 檢查是否為區塊的結束標記
                if date_pattern.match(next_line) or message_pattern.match(next_line):
                    break

                # 如果不是結束標記，且不是空行，則加入內容
                if next_line:
                    content_parts.append(next_line)

                j += 1 # 繼續掃描下一行

            # 從訊息區塊中提取標題和 URL
            full_content_str = " ".join(content_parts)
            url_match = url_pattern.search(full_content_str)

            if url_match:
                url = url_match.group(0)
                # 標題是 URL 之前的所有文字，並將多個空白符正規化為單一空格
                title_raw = full_content_str[:url_match.start()]
                title = re.sub(r'\s+', ' ', title_raw).strip()

                # 如果標題為空，使用一個預設值
                if not title:
                    title = "無標題"

                # 過濾掉教學/提醒訊息
                if "提醒小作文標題格式" in title:
                    i = j # 移動到下一個未處理的行
                    continue

                results.append({
                    'date': current_date,
                    'time': time,
                    'author': author,
                    'title': title,
                    'url': url
                })

            i = j # 移動到下一個未處理的行
        else:
            i += 1 # 如果不是訊息行，繼續下一行

    log.info(f"從聊天紀錄中解析出 {len(results)} 筆結構化資料。")
    return results


def extract_urls(text: str) -> list[str]:
    """
    [過渡時期函式]
    為了保持舊 API 的相容性，此函式現在會呼叫新的解析器，
    並只回傳網址列表。未來應直接使用 parse_chat_log。
    """
    log.warning("呼叫了過時的函式 extract_urls。請考慮切換到 parse_chat_log。")
    parsed_data = parse_chat_log(text)
    # 只回傳網址列表以維持舊的介面
    return [item['url'] for item in parsed_data]

# [2025-09-25] Jules: 在遷移到 core_service 後，
# save_urls_to_db 和 main 區塊已不再需要，因為資料庫互動
# 將完全由 DBClient 代理，且此檔案只作為模組被匯入。
