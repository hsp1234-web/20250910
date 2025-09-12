import logging
import sys
import json
import uuid
import requests
from pathlib import Path
from typing import List, Dict

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks, Depends
from pydantic import BaseModel

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection
from core import key_manager, prompt_manager
from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- Pydantic 模型 ---
class AnalysisRequest(BaseModel):
    file_ids: List[int]
    model_name: str # 新增 model_name 欄位

# --- WebSocket 通知輔助函式 ---
def _send_websocket_notification(server_port: int, message: Dict):
    """向主伺服器的內部端點發送通知。"""
    try:
        url = f"http://127.0.0.1:{server_port}/api/internal/notify_task_update"
        response = requests.post(url, json=message, timeout=5)
        response.raise_for_status()
    except requests.RequestException as e:
        log.error(f"無法發送 WebSocket 通知: {e}")

# --- 背景任務函式 ---
def run_ai_analysis_task(file_ids: List[int], server_port: int, model_name: str):
    """
    對多個檔案執行新的兩階段 AI 分析流程。
    """
    log.info(f"背景任務：開始分析 {len(file_ids)} 個檔案，使用模型: {model_name}...")

    # 1. 初始化工具 (一次性)
    all_prompts = prompt_manager.get_all_prompts()
    stage_1_prompt_template = all_prompts.get("stage_1_extraction_prompt")
    stage_2_prompt_template = all_prompts.get("stage_2_generation_prompt")

    if not stage_1_prompt_template or not stage_2_prompt_template:
        log.error("背景任務：找不到第一階段或第二階段的提示詞，任務中止。")
        _send_websocket_notification(server_port, {
            "type": "ANALYSIS_COMPLETE", "status": "failed",
            "message": "錯誤：找不到必要的提示詞，請在提示詞管理頁面設定。"
        })
        return

    try:
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise ValueError("在金鑰池中找不到任何有效的 API 金鑰。")
        gemini = GeminiManager(api_keys=valid_keys)
    except (ImportError, ValueError) as e:
        log.error(f"背景任務：無法初始化 Gemini 管理器: {e}")
        _send_websocket_notification(server_port, {
            "type": "ANALYSIS_COMPLETE", "status": "failed",
            "message": f"錯誤：{e}"
        })
        return

    total_files = len(file_ids)
    for i, file_id in enumerate(file_ids):
        conn = None
        try:
            # --- 進度通知 ---
            progress_message = f"({i+1}/{total_files}) 正在處理檔案 ID: {file_id} (模型: {model_name})..."
            log.info(progress_message)
            _send_websocket_notification(server_port, {"type": "ANALYSIS_PROGRESS", "message": progress_message})

            # --- 獲取檔案內容 ---
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE extracted_urls SET status = 'analyzing', status_message = ? WHERE id = ?", (progress_message, file_id))
            conn.commit()

            cursor.execute("SELECT source_text, local_path FROM extracted_urls WHERE id = ?", (file_id,))
            file_data = cursor.fetchone()
            if not file_data:
                raise ValueError(f"在資料庫中找不到 ID 為 {file_id} 的檔案資料。")

            text_content = file_data['source_text'] or ""
            file_name = Path(file_data['local_path']).name if file_data['local_path'] else f"file_{file_id}"

            # --- 第一階段：結構化資料提取 ---
            _send_websocket_notification(server_port, {"type": "ANALYSIS_PROGRESS", "message": f"({i+1}/{total_files}) 檔案 {file_name}: 執行第一階段 AI 資料提取..."})
            stage_1_prompt = stage_1_prompt_template.format(document_text=text_content)
            # 使用傳入的 model_name
            structured_data = gemini.prompt_for_json(prompt=stage_1_prompt, model_name=model_name)
            if not structured_data:
                raise RuntimeError("第一階段 AI 資料提取失敗，回傳內容為空。")

            # --- 本地計算 (模擬) ---
            _send_websocket_notification(server_port, {"type": "ANALYSIS_PROGRESS", "message": f"({i+1}/{total_files}) 檔案 {file_name}: 執行本地回測計算..."})
            # 在此處插入真實的回測或其他計算邏輯
            # 為了演示，我們只回傳一些模擬數據
            backtest_results = {
                "final_return": "15.7%", "max_drawdown": "-8.2%", "sharpe_ratio": "1.2"
            }

            # --- 第二階段：HTML 報告生成 ---
            _send_websocket_notification(server_port, {"type": "ANALYSIS_PROGRESS", "message": f"({i+1}/{total_files}) 檔案 {file_name}: 執行第二階段 AI 報告生成..."})
            data_package = {
                "structured_data": structured_data,
                "backtest_results": backtest_results,
                "original_text": text_content[:500] + '...' # 僅傳遞部分原文以節省 token
            }
            stage_2_prompt = stage_2_prompt_template.format(data_package=json.dumps(data_package, ensure_ascii=False, indent=2))
            # 第二階段模型可以保持固定，或未來也做成可選
            report_html = gemini.prompt_for_text(prompt=stage_2_prompt)
            if not report_html:
                raise RuntimeError("第二階段 AI 報告生成失敗，回傳內容為空。")

            # --- 儲存報告 ---
            report_dir = SRC_DIR.parent / "reports"
            report_dir.mkdir(exist_ok=True)
            report_filename = f"report_{file_id}_{uuid.uuid4().hex[:8]}.html"
            report_path = report_dir / report_filename
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_html)

            # --- 更新資料庫 ---
            cursor.execute(
                "INSERT INTO reports (source_url_id, prompt_key, report_path, structured_data) VALUES (?, ?, ?, ?)",
                (file_id, model_name, str(report_path), json.dumps(structured_data, ensure_ascii=False))
            )
            cursor.execute("UPDATE extracted_urls SET status = 'analyzed', status_message = '分析完成' WHERE id = ?", (file_id,))
            conn.commit()
            log.info(f"檔案 {file_name} (ID: {file_id}) 分析成功，報告已儲存至 {report_path}")

        except Exception as e:
            log.error(f"背景任務：AI 分析檔案 ID {file_id} 時發生嚴重錯誤: {e}", exc_info=True)
            error_message = f"分析失敗: {type(e).__name__}: {str(e)}"
            if conn:
                try:
                    cursor = conn.cursor()
                    # 獲取目前的重試次數
                    cursor.execute("SELECT retry_count FROM extracted_urls WHERE id = ?", (file_id,))
                    row = cursor.fetchone()
                    current_retry_count = row['retry_count'] if row else 0

                    if current_retry_count < 3:
                        # 更新為等待重試狀態
                        log.info(f"檔案 ID {file_id} 分析失敗，將其設定為等待重試狀態 (嘗試次數: {current_retry_count + 1})")
                        sql = """
                            UPDATE extracted_urls
                            SET status = 'pending_retry',
                                status_message = ?,
                                retry_count = retry_count + 1,
                                last_error_details = ?
                            WHERE id = ?
                        """
                        cursor.execute(sql, (error_message, str(e), file_id))
                    else:
                        # 重試次數已達上限，標記為永久失敗
                        log.warning(f"檔案 ID {file_id} 已達最大重試次數，將其標記為永久錯誤。")
                        sql = """
                            UPDATE extracted_urls
                            SET status = 'error',
                                status_message = ?
                            WHERE id = ?
                        """
                        cursor.execute(sql, (f"已達最大重試次數。最終錯誤: {error_message}", file_id))

                    conn.commit()
                except Exception as db_err:
                    log.error(f"在處理 AI 分析錯誤時，更新資料庫失敗: {db_err}")

            _send_websocket_notification(server_port, {"type": "ANALYSIS_PROGRESS", "message": f"錯誤：處理檔案 ID {file_id} 時失敗 - {error_message}"})
        finally:
            if conn:
                conn.close()

    # --- 所有任務完成後發送最終通知 ---
    final_message = f"分析流程完成。總共 {total_files} 個檔案已處理完畢。"
    log.info(final_message)
    _send_websocket_notification(server_port, {"type": "ANALYSIS_COMPLETE", "message": final_message})


@router.get("/models")
async def get_available_models():
    """回傳可用於分析的 AI 模型列表。"""
    # 在未來，這可以從設定檔或更複雜的來源讀取
    return [
        "gemini-2.0-flash",
        "gemini-1.5-pro-latest",
        "gemini-1.5-flash-latest",
    ]

@router.get("/processed_files")
async def get_processed_files():
    """獲取所有可供分析或已分析的檔案列表（狀態為 'processed', 'analyzed', 'error', 'pending_retry'）。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 選擇所有相關狀態的檔案
        sql = """
            SELECT id, url, local_path, status, status_message
            FROM extracted_urls
            WHERE status IN ('processed', 'analyzed', 'error', 'pending_retry')
            ORDER BY created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()

        results = []
        for row in rows:
            if row['local_path']:
                results.append({
                    "id": row['id'],
                    "url": row['url'],
                    "filename": Path(row['local_path']).name,
                    "status": row['status'],
                    "status_message": row['status_message']
                })
        return results
    except Exception as e:
        log.error(f"API: 獲取已處理檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已處理檔案時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()

@router.get("/report_details/{report_id}")
async def get_report_details(report_id: int):
    """根據報告 ID 獲取其詳細的結構化 JSON 資料。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT structured_data FROM reports WHERE id = ?", (report_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="找不到指定 ID 的報告。")

        # structured_data 欄位儲存的是 JSON 字串，需要解析
        if not row['structured_data']:
            return {} # 如果沒有資料，回傳空物件

        return json.loads(row['structured_data'])

    except json.JSONDecodeError:
        log.error(f"API: 解析報告 ID {report_id} 的 JSON 資料時失敗。")
        raise HTTPException(status_code=500, detail="無法解析儲存的 JSON 資料。")
    except Exception as e:
        log.error(f"API: 獲取報告詳情時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取報告詳情時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()

@router.post("/start_analysis")
async def start_analysis(request: Request, payload: AnalysisRequest, background_tasks: BackgroundTasks):
    """接收多個檔案 ID 和一個模型名稱，為其建立背景分析任務。"""
    if not payload.file_ids:
        raise HTTPException(status_code=400, detail="檔案 ID 列表不可為空。")
    if not payload.model_name:
        raise HTTPException(status_code=400, detail="必須提供模型名稱。")

    log.info(f"API: 收到 AI 分析請求，共 {len(payload.file_ids)} 個檔案，使用模型: {payload.model_name}。")

    # 檢查是否有有效的金鑰
    if not key_manager.get_all_valid_keys_for_manager():
        raise HTTPException(status_code=428, detail="金鑰池中沒有有效的 API 金鑰。請先至「金鑰管理」頁面新增並驗證金鑰。")

    server_port = request.app.state.server_port
    if not server_port:
        raise HTTPException(status_code=500, detail="無法確定伺服器埠號，無法啟動背景任務。")

    # 將 model_name 傳遞給背景任務
    background_tasks.add_task(run_ai_analysis_task, payload.file_ids, server_port, payload.model_name)

    return {"message": f"已成功為 {len(payload.file_ids)} 個檔案建立背景分析任務。"}

@router.get("/reports")
async def get_reports():
    """獲取所有已生成的分析報告列表，並提供可公開訪問的 URL。"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT r.id, r.report_path, r.created_at, r.prompt_key, u.url, u.id as source_file_id
            FROM reports r
            JOIN extracted_urls u ON r.source_url_id = u.id
            ORDER BY r.created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        results = []
        for row in rows:
            report_path = Path(row['report_path'])
            results.append({
                "id": row['id'],
                "report_url": f"/reports/{report_path.name}", # 產生可公開訪問的 URL
                "created_at": row['created_at'],
                "source_url": row['url'],
                "source_file_id": row['source_file_id'],
                "prompt_key": row['prompt_key'] # 新增，用於前端顯示
            })
        return results
    except Exception as e:
        log.error(f"API: 獲取報告列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取報告列表時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
