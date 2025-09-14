# src/core/filename_utils.py
import re

from typing import Optional


def sanitize_for_filename(text: str, max_length: Optional[int] = 50) -> str:
    """
    對文字進行淨化，使其適用於檔名。
    - 保留中日韓文字、英文字母、數字、底線和連字號。
    - 將所有其他字元（包括空格）替換為底線。
    - 移除多餘的連續底線。
    - 可選擇性地截斷至指定最大長度。
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

    # 步驟 4: (新增) 根據 max_length 截斷字串
    if max_length is not None and len(sanitized_text) > max_length:
        sanitized_text = sanitized_text[:max_length]
        # 再次移除結尾可能因截斷產生的底線
        sanitized_text = sanitized_text.strip('_')

    return sanitized_text
