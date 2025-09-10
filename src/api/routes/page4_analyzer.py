import logging
import sys
from pathlib import Path
import json
import uuid

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

PROMPTS_FILE_PATH = SRC_DIR / "prompts" / "default_prompts.json"

# --- Pydantic 模型 ---
class AnalysisRequest(BaseModel):
    file_id: int
    prompt_key: str
    api_key: str # AI 金鑰需要從前端傳遞

# --- HTML 頁面路由 ---
# (這些路由現在由 ui.py 處理，此處保留空白)

# --- API 端點 ---

@router.get("/processed_files")
async def get_processed_files():
    """獲取所有狀態為 'processed' 的檔案列表。"""
    # ... (此函式內容保持不變)
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, local_path FROM extracted_urls WHERE status = 'processed' ORDER BY created_at DESC")
        rows = cursor.fetchall()
        results = [{"id": row['id'], "url": row['url'], "filename": Path(row['local_path']).name} for row in rows if row['local_path']]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取已處理檔案時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取已處理檔案時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()

@router.get("/prompts")
async def get_prompts():
    # ... (此函式內容保持不變)
    if not PROMPTS_FILE_PATH.is_file():
        raise HTTPException(status_code=404, detail="提示詞設定檔找不到。")
    try:
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail="無法讀取提示詞檔案。")

@router.post("/prompts")
async def save_prompts(request: Request):
    # ... (此函式內容保持不變)
    try:
        new_prompts = await request.json()
        with open(PROMPTS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(new_prompts, f, ensure_ascii=False, indent=4)
        return {"status": "success", "message": "提示詞已成功更新。"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"儲存提示詞檔案時發生伺服器內部錯誤: {e}")

# --- 背景任務函式 ---
def run_ai_analysis_task(file_id: int, prompt_key: str, api_key: str):
    # --- 延遲導入 (Lazy Import) ---
    from tools.document_analyzer import analyze_document
    from tools.report_generator import generate_html_report_from_data

    log.info(f"背景任務：開始分析檔案 ID: {file_id}, 使用提示詞: {prompt_key}")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # 1. 獲取檔案內容
        cursor.execute("SELECT source_text, extracted_image_paths FROM extracted_urls WHERE id = ?", (file_id,))
        file_data = cursor.fetchone()
        if not file_data:
            raise ValueError(f"在資料庫中找不到 ID 為 {file_id} 的檔案資料。")

        text_content = file_data['source_text'] or ""
        image_paths = json.loads(file_data['extracted_image_paths'] or "[]")

        # 2. 執行 AI 分析
        ai_analysis_result = analyze_document(text_content, image_paths, api_key)

        # 3. 準備報告資料
        report_data = {
            "original_content": {"text": text_content, "image_paths": image_paths},
            "ai_analysis": ai_analysis_result
        }

        # 4. 生成 HTML 報告
        report_html = generate_html_report_from_data(report_data, title=f"文件分析報告 - {Path(image_paths[0]).parent.name if image_paths else '未知文件'}")

        # 5. 儲存報告並記錄到資料庫
        report_dir = SRC_DIR.parent / "reports"
        report_dir.mkdir(exist_ok=True)
        report_filename = f"report_{file_id}_{uuid.uuid4().hex[:8]}.html"
        report_path = report_dir / report_filename

        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_html)

        log.info(f"報告已儲存至: {report_path}")

        # 存入 reports 資料表
        cursor.execute(
            "INSERT INTO reports (source_url_id, prompt_key, report_path) VALUES (?, ?, ?)",
            (file_id, prompt_key, str(report_path))
        )
        conn.commit()

    except Exception as e:
        log.error(f"背景任務：AI 分析檔案 ID {file_id} 時發生嚴重錯誤: {e}", exc_info=True)
        # 可選：更新原始檔案的狀態以反映錯誤
        if conn:
            cursor.execute("UPDATE extracted_urls SET status_message = ? WHERE id = ?", (f"AI分析失敗: {e}", file_id))
            conn.commit()
    finally:
        if conn:
            conn.close()

@router.post("/start_analysis")
async def start_analysis(payload: AnalysisRequest, background_tasks: BackgroundTasks):
    log.info(f"API: 收到 AI 分析請求，檔案 ID: {payload.file_id}")
    background_tasks.add_task(run_ai_analysis_task, payload.file_id, payload.prompt_key, payload.api_key)
    return JSONResponse(content={"message": f"已成功為檔案 ID {payload.file_id} 建立背景分析任務。"})

@router.get("/reports")
async def get_reports():
    """獲取所有已生成的分析報告列表。"""
    log.info("API: 收到獲取報告列表的請求。")
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # 連接 reports 和 extracted_urls 來獲取原始檔名
        sql = """
            SELECT r.id, r.report_path, r.created_at, u.url
            FROM reports r
            JOIN extracted_urls u ON r.source_url_id = u.id
            ORDER BY r.created_at DESC
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        results = [{"id": row['id'], "report_path": row['report_path'], "created_at": row['created_at'], "source_url": row['url']} for row in rows]
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"API: 獲取報告列表時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="獲取報告列表時發生伺服器內部錯誤。")
    finally:
        if conn:
            conn.close()
