import logging
import json
import asyncio
import httpx
import os
import sys
from pathlib import Path
from typing import Dict, Any

# --- 路徑修正 ---
# 為了能從 services 目錄中，匯入位於 src 目錄的工具模組
# 我們需要將專案的根目錄加入到 Python 的搜尋路徑中
# services/document_processor_service/ -> services/ -> . (root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# --- 本地與專案模組匯入 ---
from services.document_processor_service.repository import update_task_status, save_successful_analysis
from src.tools.universal_downloader import download_file
from src.tools.content_extractor import extract_content

# --- 日誌與常數設定 ---
log = logging.getLogger(__name__)
LLM_SERVICE_URL = "http://127.0.0.1:8001/generate"
MODEL_NAME = "gemma2:2b"
DOWNLOAD_DIR = Path(__file__).parent / "downloads"
DOWNLOAD_DIR.mkdir(exist_ok=True)

def build_analysis_prompt(text_content: str) -> str:
    """
    建構一個詳細的提示詞，指導本地 LLM 進行文件分析，並以指定的 JSON 格式回傳結果。
    """
    # 移除多餘的空白，避免在提示詞中佔用過多 token
    cleaned_text = "\n".join(line.strip() for line in text_content.split('\n') if line.strip())

    prompt = f"""
你是一位專業的金融市場分析師。請仔細閱讀以下提供的財經報告文字，並嚴格按照指定的 JSON 格式回傳你的分析結果。

--- 文件內容開始 ---
{cleaned_text[:4000]}
--- 文件內容結束 ---

請根據文件內容，生成一個包含以下五個鍵的 JSON 物件：
1.  `summary`: (字串) 對文件內容的摘要，長度約在 50 到 100 字之間。
2.  `stock_id`: (字串) 如果內容中明確提到台股股票代號（例如 2330, 0050），請填入此代號。如果沒有提到，請回傳 `null`。
3.  `strategy`: (字串) 判斷作者對主要標的的使用策略。必須是以下五個選項之一： "看多", "看空", "多策略", "無法判斷", "空值"。
4.  `quality_score`: (整數) 根據報告的分析深度、數據支持和論述清晰度，給出 1 到 10 的評分。1 代表品質最差，10 代表品質最好。
5.  `is_trade_related`: (字串) 判斷這份文件是否與金融交易直接相關。必須是以下三個選項之一： "是", "否", "空值"。

你的回覆**必須**是一個格式正確的 JSON 物件，不要包含任何 JSON 以外的文字、解釋或註解。

JSON 格式範例：
{{
  "summary": "這是一段約50到100字的內容摘要...",
  "stock_id": "2330",
  "strategy": "看多",
  "quality_score": 8,
  "is_trade_related": "是"
}}
"""
    return prompt

async def analyze_text_with_llm(text_content: str) -> Dict[str, Any]:
    """
    使用本地 llm_service 分析文字。
    """
    prompt = build_analysis_prompt(text_content)
    payload = {"model": MODEL_NAME, "prompt": prompt}

    async with httpx.AsyncClient(timeout=300.0) as client: # 加長超時時間以應對大型模型
        try:
            log.info(f"正在向 llm_service ({LLM_SERVICE_URL}) 發送分析請求...")
            response = await client.post(LLM_SERVICE_URL, json=payload)
            response.raise_for_status()

            # llm_service 的回應本身是一個 JSON，我們需要的是裡面的 "response_text"
            llm_response_json = response.json()
            analysis_text = llm_response_json.get("response_text", "{}")

            # 解析 "response_text" 中包含的 JSON 字串
            log.info("正在解析 llm_service 回傳的分析結果...")
            # 移除可能存在於 JSON 前後的 markdown 標記
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
    執行完整的「下載 -> 拆解 -> 分析 -> 保存」工作流程。
    這是一個非同步函式，設計為在背景執行。
    """
    log.info(f"開始處理新文件，來源 URL: {source_url}")
    downloaded_path_str = None
    try:
        # 步驟 0: 更新任務狀態為處理中
        await asyncio.to_thread(update_task_status, source_url, 'processing')

        # 步驟 1: 下載文件
        log.info(f"步驟 1/4: 正在從 {source_url} 下載文件...")
        success, downloaded_path_str, message = await asyncio.to_thread(
            download_file, source_url, str(DOWNLOAD_DIR)
        )
        if not success:
            raise IOError(f"文件下載失敗: {message}")
        log.info(f"文件已成功下載至: {downloaded_path_str}")

        # 步驟 2: 拆解文件，提取內容
        log.info(f"步驟 2/4: 正在從 {downloaded_path_str} 提取內容...")
        content_data = await asyncio.to_thread(extract_content, downloaded_path_str, str(DOWNLOAD_DIR))
        if not content_data or not content_data.get("text"):
            raise ValueError("文件內容提取失敗或文件內沒有文字。")
        log.info(f"成功提取 {len(content_data['text'])} 字元的文字內容。")

        # 步驟 3: 使用本地 LLM 分析內容
        log.info("步驟 3/4: 正在使用本地 LLM 分析文件內容...")
        analysis_result = await analyze_text_with_llm(content_data["text"])
        log.info("文件內容分析完成。")

        # 步驟 4: 將成功結果保存到資料庫
        log.info("步驟 4/4: 正在將分析結果保存到資料庫...")
        await asyncio.to_thread(save_successful_analysis, source_url, analysis_result)
        log.info(f"文件處理流程已成功完成: {source_url}")

    except Exception as e:
        log.error(f"處理 {source_url} 的過程中發生無法預期的錯誤: {e}", exc_info=True)
        # 如果發生任何錯誤，更新資料庫中的任務狀態
        await asyncio.to_thread(update_task_status, source_url, 'failed', str(e))
    finally:
        # 清理下載的檔案
        if downloaded_path_str and os.path.exists(downloaded_path_str):
            try:
                # 如果是目錄（例如解壓縮的 zip），則遞迴刪除
                if os.path.isdir(downloaded_path_str):
                    import shutil
                    shutil.rmtree(downloaded_path_str)
                else:
                    os.remove(downloaded_path_str)
                log.info(f"已成功清理臨時檔案/目錄: {downloaded_path_str}")
            except OSError as e:
                log.error(f"清理臨時檔案 {downloaded_path_str} 時發生錯誤: {e}", exc_info=True)