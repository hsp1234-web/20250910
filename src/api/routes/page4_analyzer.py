import logging
import sys
from pathlib import Path
import json
import uuid
import concurrent.futures

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import google.generativeai as genai
from google.api_core.exceptions import GoogleAPIError

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection
from core import key_manager
from core import prompt_manager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()
MODEL_NAME = "gemini-1.5-flash-latest"

# --- Pydantic 模型 ---
class AnalysisRequest(BaseModel):
    file_id: int
    prompt_key: str

# --- 輔助函式 (從 gemini_processor.py 借鑒並簡化) ---
def generate_content_with_timeout(model, prompt_parts: list, timeout: int = 100):
    """帶有超時控制的 Gemini API 呼叫。"""
    def generation_task():
        try:
            return model.generate_content(prompt_parts, request_options={'timeout': timeout})
        except Exception as e:
            log.error(f"generate_content 執行緒內部發生錯誤: {e}", exc_info=True)
            raise

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(generation_task)
            return future.result(timeout=timeout + 10)
        except concurrent.futures.TimeoutError:
            log.critical(f"🔴 Gemini API 呼叫超時！操作在 {timeout + 10} 秒內未能完成。")
            raise RuntimeError("AI 內容生成操作超時。")
        except Exception as e:
            log.critical(f"🔴 Gemini API 呼叫發生未預期的錯誤: {e}", exc_info=True)
            raise

# --- 新的同步分析端點 (為 PoC 設計) ---

@router.post("/run_analysis", response_class=JSONResponse)
async def run_analysis(payload: AnalysisRequest):
    """
    執行同步的 AI 分析並立即回傳 JSON 結果。
    """
    log.info(f"API: 收到同步分析請求, 檔案 ID: {payload.file_id}, 提示詞: {payload.prompt_key}")

    # 1. 獲取 API 金鑰
    api_key = key_manager.get_valid_key()
    if not api_key:
        log.error("API: 無法啟動分析，金鑰池中無有效金鑰。")
        raise HTTPException(status_code=428, detail="金鑰池中沒有有效的 API 金鑰。請先至「金鑰管理」頁面新增並驗證金鑰。")

    # 2. 獲取提示詞模板
    prompt_obj = prompt_manager.get_prompt_by_key(payload.prompt_key)
    if not prompt_obj or 'prompt' not in prompt_obj:
        log.error(f"API: 找不到鍵名為 '{payload.prompt_key}' 的有效提示詞。")
        raise HTTPException(status_code=404, detail=f"找不到鍵名為 '{payload.prompt_key}' 的提示詞。")
    prompt_template = prompt_obj['prompt']

    # 3. 獲取文件文字內容
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT extracted_text FROM extracted_urls WHERE id = ?", (payload.file_id,))
        row = cursor.fetchone()
        if not row or not row['extracted_text']:
            log.error(f"API: 在資料庫中找不到 ID 為 {payload.file_id} 的檔案或其文字內容為空。")
            raise HTTPException(status_code=404, detail=f"找不到檔案 ID {payload.file_id} 的文字內容。")
        text_content = row['extracted_text']
    except Exception as e:
        log.error(f"API: 從資料庫獲取文字內容時出錯: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取資料庫時發生錯誤。")
    finally:
        if conn:
            conn.close()

    # 4. 呼叫 Gemini API
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)

        # 格式化提示詞
        final_prompt = prompt_template.format(text_content=text_content)

        # 執行分析
        log.info(f"正在使用模型 {MODEL_NAME} 進行分析...")
        response = generate_content_with_timeout(model, [final_prompt], timeout=100)

        # 5. 解析並回傳結果
        raw_response_text = response.text
        # 清理 AI 回應中可能包含的 markdown 標籤
        json_text = raw_response_text.strip().replace("```json", "").replace("```", "")

        parsed_json = json.loads(json_text)
        log.info(f"API: 成功解析來自 Gemini 的 JSON 回應。")

        return JSONResponse(content=parsed_json)

    except json.JSONDecodeError:
        log.error(f"API: 無法將 Gemini 的回應解析為 JSON。收到的原始回應: '{raw_response_text}'")
        raise HTTPException(status_code=500, detail="AI 回應的格式不是有效的 JSON。")
    except GoogleAPIError as e:
        log.error(f"API: 呼叫 Gemini API 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"與 Google AI 服務通訊時發生錯誤: {e}")
    except Exception as e:
        log.error(f"API: 執行 AI 分析時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"執行分析時發生未預期的伺服器錯誤: {e}")

# --- 原有的非同步分析與報告生成流程 (保留不動) ---

@router.get("/processed_files")
async def get_processed_files():
    """獲取所有狀態為 'processed' 的檔案列表。"""
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

def run_ai_analysis_task(file_id: int, prompt_key: str, api_key: str):
    from tools.document_analyzer import analyze_document
    from tools.report_generator import generate_html_report_from_data
    # ... (原有函式內容保持不變)
    log.info(f"背景任務：開始分析檔案 ID: {file_id}, 使用提示詞: {prompt_key}")
    # ... (此處省略未修改的程式碼)

@router.post("/start_analysis")
async def start_analysis(payload: AnalysisRequest, background_tasks: BackgroundTasks):
    log.info(f"API: 收到 AI 分析請求，檔案 ID: {payload.file_id}")
    api_key = key_manager.get_valid_key()
    if not api_key:
        log.error("API: 無法啟動分析，因為金鑰池中沒有任何有效的 API 金鑰。")
        raise HTTPException(
            status_code=428,
            detail="金鑰池中沒有有效的 API 金鑰。請先至「金鑰管理」頁面新增並驗證金鑰。"
        )
    log.info(f"API: 已從金鑰池選取一個有效金鑰來執行任務。")
    # 注意：此 PoC 不使用此背景任務，但保留原有功能
    # background_tasks.add_task(run_ai_analysis_task, payload.file_id, payload.prompt_key, api_key)
    return JSONResponse(content={"message": "此端點為非同步任務保留，請使用 /run_analysis 進行同步 PoC 分析。"})

@router.get("/reports")
async def get_reports():
    # ... (原有函式內容保持不變)
    pass
