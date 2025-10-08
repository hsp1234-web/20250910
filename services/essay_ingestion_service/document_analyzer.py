import logging
import json
import asyncio
import httpx
import os
import sys
from pathlib import Path
from typing import Dict, Any

# --- 本地與專案模組匯入 ---
# JULES: 這些將指向服務內部的本地副本
from .document_repository import update_task_status, save_successful_analysis
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

async def process_document_url(source_url: str):
    """
    執行完整的下載, 拆解, 分析, 保存工作流程.
    這是一個為新服務定製的, 獨立的非同步函式.
    """
    log.info(f"開始處理新文件，來源 URL: {source_url}")
    downloaded_path_str = None
    try:
        # 步驟 0: 在新資料庫中建立任務並標記為處理中
        await asyncio.to_thread(update_task_status, source_url, 'processing')

        # 步驟 1: 下載文件
        log.info(f"步驟 1/4: 正在從 {source_url} 下載文件...")
        # JULES: download_file 將是本地副本
        success, downloaded_path_str, message = await asyncio.to_thread(
            download_file, source_url, str(DOWNLOAD_DIR)
        )
        if not success:
            raise IOError(f"文件下載失敗: {message}")
        log.info(f"文件已成功下載至: {downloaded_path_str}")

        # 步驟 2: 拆解文件，提取文字和圖片
        log.info(f"步驟 2/4: 正在從 {downloaded_path_str} 提取內容...")
        # JULES: extract_content 將是本地副本
        content_data = await asyncio.to_thread(extract_content, downloaded_path_str, str(DOWNLOAD_DIR))

        text_content = content_data.get("text") if content_data else ""
        image_paths = content_data.get("image_paths") if content_data else []

        if not text_content:
            # 即使沒有文字，但有圖片，也可能需要保存
            log.warning("文件內容提取成功，但未發現文字內容。")

        log.info(f"成功提取 {len(text_content)} 字元的文字和 {len(image_paths)} 張圖片。")

        # 步驟 3: 使用本地 LLM 進行分析 (僅分析文字部分)
        analysis_result = {}
        if text_content:
            log.info("步驟 3/4: 正在使用本地 LLM 分析文件內容...")
            analysis_result = await analyze_text_with_llm(text_content)
            log.info("文件內容分析完成。")
        else:
            log.info("步驟 3/4: 跳過 LLM 分析，因為沒有文字內容。")


        # 步驟 4: 將成功結果（包括圖片路徑）保存到資料庫
        log.info("步驟 4/4: 正在將分析結果和圖片路徑保存到資料庫...")
        await asyncio.to_thread(save_successful_analysis, source_url, analysis_result, image_paths)
        log.info(f"文件處理流程已成功完成: {source_url}")

    except Exception as e:
        log.error(f"處理 {source_url} 的過程中發生無法預期的錯誤: {e}", exc_info=True)
        await asyncio.to_thread(update_task_status, source_url, 'failed', str(e))
    finally:
        # 清理下載的檔案和提取的圖片
        if downloaded_path_str and os.path.exists(downloaded_path_str):
            try:
                if os.path.isdir(downloaded_path_str):
                    import shutil
                    shutil.rmtree(downloaded_path_str)
                else:
                    os.remove(downloaded_path_str)
                log.info(f"已成功清理臨時下載檔案/目錄: {downloaded_path_str}")
            except OSError as e:
                log.error(f"清理臨時下載檔案 {downloaded_path_str} 時發生錯誤: {e}", exc_info=True)

        # JULES: 也需要清理提取出來的圖片
        # (此邏輯應在更上層或由一個單獨的清理任務處理，暫時保留)