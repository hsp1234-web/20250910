# src/core/filename_utils.py
import re

def sanitize_for_filename(text: str) -> str:
    """
    對文字進行淨化，使其適用於檔名。
    - 保留中日韓文字、英文字母、數字、底線和連字號。
    - 將所有其他字元（包括空格）替換為底線。
    - 移除多餘的連續底線。
    """
    if not text:
        return ""

    # 步驟 1: 將所有不符規則的字元換成底線
    # [^\w\-\u4e00-\u9fff] 匹配任何非 (單字字元(a-zA-Z0-9_), 連字號, 或 中日韓統一表意文字) 的字元
    sanitized_text = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', text)

    # 步驟 2: 將多個連續的底線合併為一個
    sanitized_text = re.sub(r'__+', '_', sanitized_text)

    # 步驟 3: 移除開頭和結尾的底線
    sanitized_text = sanitized_text.strip('_')

    return sanitized_text
