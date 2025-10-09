import logging
import json
import asyncio
import httpx
import os
import sys
from pathlib import Path
from typing import Dict, Any

# --- 本地與專案模組匯入 ---
# JULES: 移除對本地資料庫 repository 的依賴
from .universal_downloader import download_file
from .content_extractor import extract_content
# JULES: 暫時移除 stock_id_extractor 以簡化初始整合

# --- 日誌與常數設定 ---
log = logging.getLogger(__name__)
# JULES: 修正 - llm_service 是外部服務，不能指向自己 (8001)。將其指向一個獨立的連接埠。
LLM_SERVICE_URL = "http://127.0.0.1:8002/generate"
MODEL_NAME = "gemma2:2b" # JULES: 假設模型名稱不變
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def build_analysis_prompt(text_content: str) -> str:
    """
    建構一個詳細的提示詞，指導本地 LLM 進行文件分析，並以指定的 JSON 格式回傳結果。
    JULES: 簡化版本，暫不處理 stock_id。
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
請生成一個包含以下五個鍵的 JSON 物件：
1.  `summary`: (字串) 對文件內容的摘要，長度約在 50 到 100 字之間。
2.  `analyzed_stock_ids`: (字串列表) 請分析文本中提到的所有台股股票代號，並將它們包含在此欄位中。如果沒有，請回傳一個空列表 `[]`。
3.  `strategy`: (字串) 判斷作者對主要標的的使用策略。必須是以下五個選項之一： "看多", "看空", "多策略", "無法判斷", "空值"。
4.  `quality_score`: (整數) 根據報告的分析深度、數據支持和論述清晰度，給出 1 到 10 的評分。1 代表品質最差，10 代表品質最好。
5.  `is_trade_related`: (字串) 判斷這份文件是否與金融交易直接相關。必須是以下三個選項之一： "是", "否", "空值"。

--- 重要提醒 ---
-   你的回覆**必須**是一個格式完全正確的 JSON 物件。
-   不要包含任何 JSON 以外的文字、解釋或註解。
-   `analyzed_stock_ids` 必須是一個列表 (list)，即使裡面只有一個元素或沒有元素。

--- JSON 格式範例 ---
{{
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
    使用本地 llm_service 分析文字.
    """
    prompt = build_analysis_prompt(text_content)
    payload = {"model": MODEL_NAME, "prompt": prompt}

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            log.info(f"正在向 llm_service ({LLM_SERVICE_URL}) 發送分析請求...")
            response = await client.post(LLM_SERVICE_URL, json=payload)
            response.raise_for_status()
            llm_response_json = response.json()
            analysis_text = llm_response_json.get("response_text", "{}")
            log.info("正在解析 llm_service 回傳的分析結果...")
            cleaned_analysis_text = analysis_text.strip().removeprefix("```json").removesuffix("```").strip()
            analysis_data = json.loads(cleaned_analysis_text)
            log.info("成功解析來自 llm_service 的 JSON 結果。")
            return analysis_data
        except httpx.RequestError as e:
            log.error(f"無法連線到 llm_service: {e}", exc_info=True)
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
        log.warning("核心分析：文件內容提取成功，但未發現文字內容。")
    log.info(f"核心分析：成功提取 {len(text_content)} 字元的文字和 {len(image_paths)} 張圖片。")

    analysis_result_data = {}
    if text_content:
        log.info("核心分析：正在使用本地 LLM 分析文件內容...")
        analysis_result_data = await analyze_text_with_llm(text_content)
        log.info("核心分析：文件內容分析完成。")
    else:
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