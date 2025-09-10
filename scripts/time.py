#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
說明：
這是一個輔助腳本，專門用於生成符合專案要求的標準時間戳記。
它會獲取當前 'Asia/Taipei' 時區的時間，並以 ISO 8601 格式輸出。
這是為了確保所有 AI 助理在更新 `Log.md` 時，都能使用一致且正確的時間格式。

用法：
python scripts/time.py
"""

from datetime import datetime
import zoneinfo

def get_taipei_time_iso():
    """
    獲取當前台北時區的 ISO 8601 格式時間。

    Returns:
        str: 格式如 '2025-09-01T15:30:00+08:00' 的時間字串。
    """
    try:
        # 取得台北時區
        taipei_tz = zoneinfo.ZoneInfo("Asia/Taipei")
        
        # 獲取當前時間並應用時區
        now_utc = datetime.now(zoneinfo.ZoneInfo("UTC"))
        now_taipei = now_utc.astimezone(taipei_tz)
        
        # 格式化為 ISO 8601，並包含時區資訊
        return now_taipei.isoformat()
        
    except zoneinfo.ZoneInfoNotFoundError:
        return "錯誤：找不到 'Asia/Taipei' 時區。請確保 tzdata 在系統中可用。"
    except Exception as e:
        return f"發生未知錯誤：{e}"

if __name__ == "__main__":
    print(get_taipei_time_iso())
