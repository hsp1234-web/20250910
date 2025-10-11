import logging
import json
import asyncio
import httpx
import os
import sys
from pathlib import Path
from typing import Dict, Any

# --- 路徑修正，確保能匯入 src ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 本地與專案模組匯入 ---
from .content_extractor import extract_content
from src.core.service_discovery import get_service_url

# --- 日誌與常數設定 ---
log = logging.getLogger(__name__)
MODEL_NAME = "qwen2:1.5b"
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def build_analysis_prompt(text_content: str) -> str:
    """
    建構一個詳細的提示詞，指導本地 LLM 進行文件分析，並以指定的 JSON 格式回傳結果。
    (Jules): 根據需求，新增 title 和 author 欄位。
    """
    # 移除多餘的空白，避免在提示詞中佔用過多 token
    cleaned_text = "\n".join(line.strip() for line in text_content.split('\n') if line.strip())

    prompt = f"""
你是一位專業、謹慎的金融市場分析師。你的任務是根據提供的資訊，以絕對精確的格式回傳分析結果。

--- 已知資訊 ---
1.  **文件內容**:
    --- 文件內容開始 ---
    {cleaned_text[:4000]}
    --- 文件內容結束 ---

--- 你的任務 ---
請仔細閱讀文件內容，並嚴格按照指定的 JSON 格式回傳你的分析。

--- JSON 輸出指令 ---
請生成一個包含以下七個鍵的 JSON 物件：
1.  `title`: (字串) 從文件內容中提取出的標題。如果找不到，請回傳 "無法辨識的標題"。
2.  `author`: (字串) 從文件內容中提取出的作者。如果找不到，請回傳 "無法辨識的作者"。
3.  `summary`: (字串) 對文件內容的摘要，長度約在 50 到 100 字之間。
4.  `analyzed_stock_ids`: (字串列表) 請分析文本中提到的所有台股股票代號，並將它們包含在此欄位中。如果沒有，請回傳一個空列表 `[]`。
5.  `strategy`: (字串) 判斷作者對主要標的的使用策略。必須是以下五個選項之一： "看多", "看空", "多策略", "無法判斷", "空值"。
6.  `quality_score`: (整數) 根據報告的分析深度、數據支持和論述清晰度，給出 1 到 10 的評分。1 代表品質最差，10 代表品質最好。
7.  `is_trade_related`: (字串) 判斷這份文件是否與金融交易直接相關。必須是以下三個選項之一： "是", "否", "空值"。

--- 重要提醒 ---
-   你的回覆**必須**是一個格式完全正確的 JSON 物件。
-   不要包含任何 JSON 以外的文字、解釋或註解。
-   `analyzed_stock_ids` 必須是一個列表 (list)，即使裡面只有一個元素或沒有元素。

--- JSON 格式範例 ---
{{
  "title": "關於 AAA 公司未來三個月的走勢分析",
  "author": "分析師 王小明",
  "summary": "這是一段約50到100字的內容摘要...",
  "analyzed_stock_ids": ["3711", "2330"],
  "strategy": "看多",
  "quality_score": 8,
  "is_trade_related": "是"
}}
"""
    return prompt

async def analyze_text_with_llm(text_content: str) -> Dict[str, Any]:
    """
    使用本地 llm_service 分析文字。
    (Jules): 增強錯誤處理，捕捉因為 llm_service 無法連接 Ollama 所造成的 503 錯誤。
    """
    # 1. 動態發現 llm_service 的 URL
    llm_base_url = get_service_url("llm_service")
    if not llm_base_url:
        log.error("無法找到 'llm_service' 的 URL，分析無法進行。")
        raise ConnectionError("無法找到 'llm_service'，請檢查服務是否已啟動或註冊。")

    target_url = f"{llm_base_url}/generate"

    # 2. 準備請求內容
    prompt = build_analysis_prompt(text_content)
    payload = {"model": MODEL_NAME, "prompt": prompt}

    # 3. 發送請求
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            log.info(f"正在向 llm_service ({target_url}) 發送分析請求...")
            response = await client.post(target_url, json=payload)
            response.raise_for_status()

            # 4. 解析回應
            llm_response_json = response.json()
            analysis_text = llm_response_json.get("response_text", "{}")
            log.info("正在解析 llm_service 回傳的分析結果...")
            cleaned_analysis_text = analysis_text.strip().removeprefix("```json").removesuffix("```").strip()
            analysis_data = json.loads(cleaned_analysis_text)
            log.info("成功解析來自 llm_service 的 JSON 結果。")
            return analysis_data

        except httpx.HTTPStatusError as e:
            # (Jules): 如果下游服務 (llm_service) 回傳 503，表示它無法連接到 Ollama。
            # 我們需要捕捉這個特定的錯誤，並將其轉換為一個我們自己可以處理的 ConnectionError。
            if e.response.status_code == 503:
                log.error(f"下游的 llm_service 服務目前不可用 (可能是 Ollama 問題): {e.response.text}")
                raise ConnectionError(f"AI 分析服務 (Ollama) 目前無法使用: {e.response.text}")
            # 對於其他 HTTP 錯誤，則重新引發它們
            raise e
        except httpx.RequestError as e:
            log.error(f"無法連線到 llm_service ({target_url}): {e}", exc_info=True)
            raise ConnectionError(f"無法連線到 llm_service: {e}")
        except json.JSONDecodeError as e:
            log.error(f"無法解析來自 llm_service 的回應: {analysis_text}", exc_info=True)
            raise ValueError(f"llm_service 回傳的不是有效的 JSON: {e}")

# (Jules @ 2025-10-09) 重構，移除所有本地資料庫操作，使此服務成為一個純粹的分析引擎。
async def _perform_analysis(file_path: str) -> Dict[str, Any]:
    """
    (內部核心函式) 負責執行分析的核心步驟：提取、分析、並回傳結果。
    此函式不處理資料庫操作或文件清理，僅專注於分析。
    """
    log.info(f"核心分析：正在從 {file_path} 提取內容...")
    content_data = await asyncio.to_thread(extract_content, file_path, str(DOWNLOAD_DIR))
    text_content = content_data.get("text", "") if content_data else ""
    image_paths = content_data.get("image_paths", []) if content_data else []

    if not text_content:
        log.warning("核心分析：文件內容提取成功，但未發現文字內容。這將被視為一個可處理的錯誤。")
        # (Jules @ 2025-10-11) 核心修正：當沒有文字內容時，回傳一個包含明確錯誤訊息的物件。
        # 這使得上游的 API 閘道可以捕捉到這個「失敗」狀態，而不是將其視為靜默的成功。
        return {
            "error": "不支援的檔案類型或內容為空",
            "error_details": "內容提取工具無法從此檔案中讀取任何文字，因此無法進行分析。",
            "analysis_data": {},
            "image_paths": image_paths,
            "extracted_text": ""
        }

    log.info(f"核心分析：成功提取 {len(text_content)} 字元的文字和 {len(image_paths)} 張圖片。")

    analysis_result_data = {}
    if text_content:
        log.info("核心分析：正在使用本地 LLM 分析文件內容...")
        analysis_result_data = await analyze_text_with_llm(text_content)
        log.info("核心分析：文件內容分析完成。")
    else:
        # 這個分支理論上因為上面的錯誤處理而無法到達，但保留它以確保代碼的穩健性。
        log.info("核心分析：跳過 LLM 分析，因為沒有文字內容。")

    # 組合並回傳一個包含所有分析產物的字典，以便 API 閘道進行後續處理
    return {
        "analysis_data": analysis_result_data,
        "image_paths": image_paths,
        "extracted_text": text_content
    }

async def process_local_document(file_path: str) -> Dict[str, Any]:
    """
    【由本地檔案觸發】執行拆解、分析、並回傳結果。
    此版本不會刪除傳入的 file_path，並會在發生錯誤時向上拋出異常，由呼叫者處理。
    """
    log.info(f"開始處理本地文件，路徑: {file_path}")
    if not Path(file_path).exists():
        err_msg = f"檔案不存在: {file_path}"
        log.error(err_msg)
        raise FileNotFoundError(err_msg)

    try:
        # 呼叫核心分析邏輯並直接回傳結果
        return await _perform_analysis(file_path)
    except Exception as e:
        log.error(f"處理本地文件 {file_path} 的過程中發生錯誤: {e}", exc_info=True)
        # 將異常向上拋出，以便 API 端點可以捕獲它並回傳 500 錯誤給 API 閘道
        raise