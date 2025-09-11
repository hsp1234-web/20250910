# -*- coding: utf-8 -*-
"""
一個集中的時間工具模組，用於處理整個應用程式中的時區和時間格式化。
"""

from datetime import datetime
import zoneinfo
from dateutil import parser as date_parser

TAIPEI_TZ = zoneinfo.ZoneInfo("Asia/Taipei")

def get_current_taipei_time() -> datetime:
    """
    獲取當前 'Asia/Taipei' 時區的 datetime 物件。
    這個物件會包含正確的時區資訊。
    """
    try:
        now_utc = datetime.now(zoneinfo.ZoneInfo("UTC"))
        return now_utc.astimezone(TAIPEI_TZ)
    except zoneinfo.ZoneInfoNotFoundError:
        # 在一個不太可能發生的情況下，如果時區資料遺失，則回退
        print("警告：找不到 'Asia/Taipei' 時區。回退到使用 UTC。")
        return datetime.now(zoneinfo.ZoneInfo("UTC"))

def get_current_taipei_time_iso() -> str:
    """
    獲取當前台北時區的 ISO 8601 格式時間字串。
    這是寫入資料庫或進行 API 傳輸時的首選格式。
    """
    return get_current_taipei_time().isoformat()

def format_iso_for_filename(iso_string: str) -> str:
    """
    將一個 ISO 格式的時間字串（可能包含時區）轉換為檔名所需的安全格式。
    例如：'2025-09-11T09:30:00+08:00' -> '2025-09-11T09-30-00'
    """
    if not iso_string:
        # 提供一個備用值，以避免檔名產生失敗
        return get_current_taipei_time().strftime('%Y-%m-%dT%H-%M-%S')

    try:
        # dateutil.parser 可以智慧地解析幾乎所有格式的日期字串
        dt_object = date_parser.parse(iso_string)

        # 如果傳入的字串沒有時區資訊，我們假設它就是台北時間
        if dt_object.tzinfo is None:
            # 使用 .replace(tzinfo=...) 來讓 naive datetime 物件變成 aware
            dt_object = dt_object.replace(tzinfo=TAIPEI_TZ)

        # 將其轉換為台北時區以確保一致性
        dt_taipei = dt_object.astimezone(TAIPEI_TZ)

        # 格式化為檔名所需的安全格式
        return dt_taipei.strftime('%Y-%m-%dT%H-%M-%S')
    except (ValueError, TypeError) as e:
        print(f"警告：無法解析時間字串 '{iso_string}' ({e})。回退到使用當前時間。")
        # 如果解析失敗，回退到使用當前時間，以確保功能不中斷
        return get_current_taipei_time().strftime('%Y-%m-%dT%H-%M-%S')
