import logging
import sys
import json
from pathlib import Path
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Request

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

# --- 核心模組匯入 ---
from db.client import get_client
from db.database import get_db_connection

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
DB_CLIENT = get_client()

@router.get("/performance_reports", response_model=List[Dict[str, Any]])
async def get_performance_reports():
    """
    獲取所有已完成的量化分析報告數據，用於填充績效儀表板。
    """
    log.info("正在獲取所有績效報告...")
    try:
        # 1. 從資料庫獲取所有已完成的分析任務
        # 我們選擇 stage1_status 為 completed 的任務，因為量化分析在第一階段後就已完成
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, source_document_id, stage1_json_path
            FROM analysis_tasks
            WHERE stage1_status = 'completed' AND stage1_json_path IS NOT NULL
            ORDER BY created_at DESC
        """)
        tasks = cursor.fetchall()
        conn.close()

        reports = []
        for task in tasks:
            task_id = task['id']
            json_path = Path(task['stage1_json_path'])

            if not json_path.exists():
                log.warning(f"任務 {task_id} 的 JSON 檔案不存在於路徑: {json_path}，跳過此報告。")
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                stage1_data = json.load(f)

            quant_data = stage1_data.get("quantitative_analysis")

            # 只有在量化分析成功時才加入報告列表
            if quant_data and not quant_data.get("error"):
                # 獲取原始文章資訊
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT author, message_date FROM extracted_urls WHERE id = ?", (task['source_document_id'],))
                source_info = cursor.fetchone()
                conn.close()

                # 移除 quantitative_analysis，因為它包含 chart_html，可能很大
                ai_summary_data = {k: v for k, v in stage1_data.items() if k != "quantitative_analysis"}

                report_item = {
                    "task_id": task_id,
                    "title": stage1_data.get("title", "無標題"),
                    "symbol": stage1_data.get("symbol", "N/A"),
                    "source_author": source_info['author'] if source_info else '未知',
                    "source_date": source_info['message_date'] if source_info else '未知',
                    "backtest_kpis": quant_data.get("stats"),
                    "chart_html": quant_data.get("chart_html"),
                    "ai_summary": ai_summary_data, # 新增 AI 分析摘要
                    "health_score": 0 # 暫時預留，未來可計算
                }
                reports.append(report_item)

        log.info(f"成功收集到 {len(reports)} 份績效報告。")
        return reports

    except Exception as e:
        log.error(f"獲取績效報告時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")
