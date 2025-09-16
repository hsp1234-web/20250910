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
# V4 優化：全面改用依賴注入
from db.client import DBClient
from ..dependencies import get_db
from fastapi import Depends

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

@router.get("/performance_reports", response_model=List[Dict[str, Any]])
async def get_performance_reports(db: DBClient = Depends(get_db)):
    """
    (V4 優化後) 獲取所有已完成的量化分析報告數據，用於填充績效儀表板。
    """
    log.info("正在獲取所有績效報告...")
    try:
        # 透過單一請求獲取所有需要的數據
        tasks = db.get_performance_dashboard_data()

        reports = []
        for task in tasks:
            task_id = task['id']
            json_path = Path(task['stage1_json_path'])

            if not json_path.exists():
                log.warning(f"任務 {task_id} 的 JSON 檔案不存在於路徑: {json_path}，跳過此報告。")
                continue

            with open(json_path, "r", encoding="utf-8") as f:
                stage1_data = json.load(f)

            quant_data = stage1_data.get("performance_analysis")

            # 只有在量化分析成功時才加入報告列表
            if quant_data and not quant_data.get("error"):
                # 移除量化分析的部分，因為我們要把整個 stage1_data 都傳給前端
                ai_summary_data = stage1_data.copy()
                ai_summary_data.pop("performance_analysis", None)

                report_item = {
                    "task_id": task_id,
                    "title": stage1_data.get("title", "無標題"),
                    "symbol": stage1_data.get("symbol", "N/A"),
                    "source_author": task.get('author', '未知'),
                    "source_date": task.get('message_date', '未知'),
                    "backtest_kpis": quant_data.get("stats"),
                    "chart_html": quant_data.get("chart_html"),
                    "stage1_result_json": ai_summary_data,
                    "health_score": 0 # 暫時預留，未來可計算
                }
                reports.append(report_item)

        log.info(f"成功收集到 {len(reports)} 份績效報告。")
        return reports

    except Exception as e:
        log.error(f"獲取績效報告時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")
