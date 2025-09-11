# src/db/analysis_manager.py
import sqlite3
import logging
from typing import List, Dict, Any

# --- 路徑修正與模組匯入 ---
from .database import get_db_connection

log = logging.getLogger(__name__)

def create_analysis_task(source_document_id: int) -> int | None:
    """
    在 analysis_tasks 資料表中建立一個新的分析任務。

    :param source_document_id: 來源文件的 ID。
    :return: 新建立的任務 ID，如果失敗則回傳 None。
    """
    sql = "INSERT INTO analysis_tasks (source_document_id, status) VALUES (?, 'PENDING')"
    conn = get_db_connection()
    if not conn: return None
    log.info(f"DB: 準備為文件 ID {source_document_id} 建立新的分析任務。")
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(sql, (source_document_id,))
            new_task_id = cursor.lastrowid
        log.info(f"✅ 已成功建立分析任務，ID: {new_task_id}")
        return new_task_id
    except sqlite3.Error as e:
        log.error(f"❌ 建立分析任務時發生資料庫錯誤: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

def update_analysis_task(task_id: int, updates: Dict[str, Any]) -> bool:
    """
    更新一個分析任務的特定欄位。

    :param task_id: 要更新的任務 ID。
    :param updates: 一個包含要更新的欄位和新值的字典。
    :return: 如果成功更新則回傳 True，否則回傳 False。
    """
    if not updates:
        return False

    # 確保 updated_at 會自動更新
    updates['updated_at'] = sqlite3.datetime.datetime.now()

    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    params = list(updates.values())
    params.append(task_id)

    sql = f"UPDATE analysis_tasks SET {set_clause} WHERE id = ?"

    conn = get_db_connection()
    if not conn: return False

    try:
        with conn:
            conn.execute(sql, params)
        log.info(f"✅ 分析任務 {task_id} 已更新: {list(updates.keys())}")
        return True
    except sqlite3.Error as e:
        log.error(f"❌ 更新分析任務 {task_id} 時發生錯誤: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()

def get_all_analysis_tasks() -> List[Dict[str, Any]]:
    """
    獲取資料庫中所有分析任務的列表。

    :return: 一個包含所有任務字典的列表。
    """
    sql = "SELECT id, status, source_document_id, health_score, final_report_path, error_message, created_at, updated_at FROM analysis_tasks ORDER BY created_at DESC"
    conn = get_db_connection()
    if not conn: return []
    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        tasks = cursor.fetchall()
        # 將 Row 物件轉換為標準字典列表
        return [dict(task) for task in tasks]
    except sqlite3.Error as e:
        log.error(f"❌ 獲取所有分析任務時發生錯誤: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()
