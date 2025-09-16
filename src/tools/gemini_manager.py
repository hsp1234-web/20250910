# src/tools/gemini_manager.py
import logging
import json
import time
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    from PIL import Image
    # 匯入我們重構後的智慧型金鑰管理器
    from core.key_manager import key_manager
except ImportError as e:
    logging.warning(f"無法匯入所需模組: {e}。AI 分析功能將被停用。")
    genai = None
    Image = None
    GenerationConfig = None
    key_manager = None

class GeminiManager:
    """
    管理與 Google Gemini API 的所有互動。
    透過與 KeyManager 協作，實現基於資料庫的智慧型金鑰輪換和冷卻機制。
    """
    def __init__(self, timeout: int = 180, max_retries: int = 3, cooldown_seconds: int = 60, max_key_attempts: int = 20):
        if not genai or not key_manager:
            raise ImportError("GeminiManager 無法初始化，因為 google.generativeai 或 key_manager 未正確載入。")

        self.timeout = timeout
        self.max_retries = max_retries  # 針對單一金鑰的重試次數
        self.cooldown_seconds = cooldown_seconds
        self.max_key_attempts = max_key_attempts # 最多嘗試多少個不同的金鑰
        logging.info("Gemini 管理器已初始化，將使用外部 KeyManager 進行金鑰管理。")

    def list_available_models(self) -> List[str]:
        """
        列出所有支援 'generateContent' 方法的可用 Gemini 模型。
        會從 KeyManager 獲取一個金鑰來進行查詢。
        """
        if not genai:
            logging.warning("無法列出模型，因為 google.generativeai 未安裝。")
            return []

        # 從 KeyManager 獲取一個金鑰
        api_key_dict = key_manager.get_key()
        if not api_key_dict:
            raise ConnectionError("無法列出模型，因為 KeyManager 未能提供任何可用的 API 金鑰。")

        key_name = api_key_dict['name']
        key_value = api_key_dict['value']
        logging.info(f"正在使用金鑰 '{key_name}' 查詢可用的模型...")

        try:
            genai.configure(api_key=key_value)
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            logging.info(f"查詢成功，找到 {len(available_models)} 個可用模型。")
            return available_models
        except Exception as e:
            logging.error(f"使用金鑰 '{key_name}' 查詢模型時發生錯誤: {e}", exc_info=True)
            # 如果查詢模型失敗，可能是金鑰本身的問題，也將其冷卻
            key_manager.set_key_cooldown(key_name, self.cooldown_seconds)
            raise e

    def _api_call_wrapper(self, task_name: str, model_name: str, prompt_content: List[Any], output_format: str = 'json'):
        if not genai:
            return None, None, "google.generativeai not installed", "N/A", 0

        last_error = None

        for i in range(self.max_key_attempts):
            # 1. 從 KeyManager 獲取一個可用金鑰
            api_key_dict = key_manager.get_key()
            if not api_key_dict:
                logging.error(f"[{task_name}] 金鑰池已完全耗盡，在嘗試 {i} 次後終止。")
                return None, ValueError("金鑰池已耗盡"), "all_keys_failed", 0

            key_name = api_key_dict['name']
            key_value = api_key_dict['value']
            tag = f"{task_name}-{key_name}"
            logging.info(f"[{tag}] 準備使用金鑰 (嘗試 {i + 1}/{self.max_key_attempts}) 執行 API 請求...")

            try:
                genai.configure(api_key=key_value)
            except Exception as e:
                logging.error(f"[{tag}] 設定金鑰時發生嚴重錯誤: {e}，將此金鑰設為冷卻並嘗試下一個。")
                key_manager.set_key_cooldown(key_name, self.cooldown_seconds)
                last_error = e
                continue # 嘗試下一個金鑰

            generation_config = GenerationConfig(response_mime_type="application/json") if output_format == 'json' else None

            # 2. 對單一金鑰進行內部重試
            for attempt in range(self.max_retries):
                logging.info(f"[{tag}] 正在執行第 {attempt + 1}/{self.max_retries} 次嘗試 (模型: {model_name})...")
                try:
                    model = genai.GenerativeModel(model_name)
                    response = model.generate_content(
                        prompt_content,
                        generation_config=generation_config,
                        request_options={'timeout': self.timeout}
                    )
                    raw_text = response.text
                    if not raw_text:
                        raise ValueError("API 回傳空內容")

                    logging.info(f"[{tag}] API 請求成功。")

                    token_usage = 0
                    try:
                        if hasattr(response, 'usage_metadata') and response.usage_metadata:
                            if hasattr(response.usage_metadata, 'total_token_count'):
                                token_usage = response.usage_metadata.total_token_count
                            elif hasattr(response.usage_metadata, 'get'):
                                token_usage = response.usage_metadata.get('total_token_count', 0)
                    except Exception as e:
                        logging.warning(f"[{tag}] 無法從 usage_metadata 中獲取 token 消耗: {e}")

                    if output_format == 'json':
                        clean_text = raw_text
                        if clean_text.strip().startswith("```json"):
                            clean_text = clean_text.strip()[7:-3].strip()
                        # 回傳解析後的物件、原始文字、金鑰名稱和 token 用量
                        return json.loads(clean_text), raw_text, None, key_name, token_usage
                    else: # 'text'
                        clean_text = raw_text
                        if clean_text.strip().startswith("```html"):
                            clean_text = clean_text.strip()[7:-3].strip()
                        elif clean_text.strip().startswith("```"):
                            clean_text = clean_text.strip()[3:-3].strip()
                        # 回傳處理後的文字、原始文字、金鑰名稱和 token 用量
                        return clean_text, raw_text, None, key_name, token_usage

                except Exception as e:
                    last_error = e
                    last_error_str = f"{type(e).__name__}: {e}".lower()

                    is_rate_limit_error = any(s in last_error_str for s in ["quota", "resourceexhausted", "429"])

                    if is_rate_limit_error:
                        logging.error(f"[{tag}] 遭遇配額耗盡錯誤。通知 KeyManager 將此金鑰移至冷卻區。")
                        key_manager.set_key_cooldown(key_name, self.cooldown_seconds)
                        break # 跳出內層重試迴圈，去獲取下一個金鑰

                    # 對於其他可重試的錯誤
                    if attempt < self.max_retries - 1:
                        wait_time = 2**(attempt + 1)
                        logging.warning(f"[{tag}] 遭遇暫時性錯誤: {last_error_str}，{wait_time} 秒後重試...");
                        time.sleep(wait_time)
                    else: # 最後一次重試仍然失敗
                        logging.error(f"[{tag}] 金鑰在所有重試後依然失敗。")
                        break # 跳出內層重試迴圈

            # 如果內層迴圈是因為錯誤而 break（而不是 return），則繼續外層迴圈以獲取新金鑰
            continue

        logging.error(f"[{task_name}] 在嘗試了 {self.max_key_attempts} 組金鑰後，API 請求最終失敗。最後一個錯誤: {last_error}")
        return None, None, last_error, "all_keys_failed", 0

    def prompt_for_json(self, prompt: str, model_name: str = "gemini-2.0-flash") -> Optional[Dict]:
        """
        使用自訂提示詞執行請求，並期望回傳一個 JSON 物件。
        適用於第一階段的結構化資料提取。
        """
        # 說明：修改回傳值，使其從只回傳 result，變為回傳完整的 (result, error, used_key) 元組。
        # 這是為了解決下游函式無法正確接收到錯誤狀態的問題。
        return self._api_call_wrapper(
            task_name="PromptForJson",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='json'
        )

    def prompt_for_text(self, prompt: str, model_name: str = "gemini-1.5-pro-latest") -> Optional[str]:
        """
        使用自訂提示詞執行請求，並期望回傳純文字 (例如 HTML)。
        適用於第二階段的報告生成。
        """
        # 說明：同樣修改回傳值，使其回傳完整的 (result, error, used_key) 元組。
        return self._api_call_wrapper(
            task_name="PromptForText",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='text'
        )

    def analyze_text(self, text_content: str, model_name: str = "gemini-1.5-flash-latest") -> Optional[Dict]:
        """【舊版，可選刪除】分析文字並回傳摘要和關鍵字。"""
        prompt = f"你是一位專業的內容分析師。請閱讀以下文章，並以 JSON 格式回傳包含以下兩個鍵的物件：1. `summary` (string): 對文章內容的簡短摘要。2. `keywords` (list of strings): 從文章中提取的 3-5 個核心關鍵字。\\n\\n文章內容如下：\\n---\\n{text_content}\\n---\\n請直接回傳 JSON 物件，不要包含任何額外的解釋或 Markdown 標記。"
        return self.prompt_for_json(prompt, model_name)

    def describe_image(self, image_path: str, model_name: str = "gemini-1.5-flash-latest") -> Optional[Dict]:
        """【舊版，可選刪除】描述圖片內容。"""
        if not Image:
            return None
        try:
            img = Image.open(image_path)
        except Exception as e:
            logging.error(f"無法開啟圖片檔案 '{image_path}': {e}")
            return None

        prompt = "你是一位圖像分析專家。請描述這張圖片的內容。如果它是一張圖表，請說明它的類型以及它可能在傳達的資訊。\\n請以 JSON 格式回傳包含以下兩個鍵的物件：1. `description` (string): 對圖片內容的詳細描述。2. `chart_type` (string): 如果是圖表，請指出其類型（例如 '長條圖', '折線圖', '圓餅圖'）。如果不是圖表，則回傳 '非圖表'。"
        result, _, _, _ = self._api_call_wrapper(
            task_name="DescribeImage",
            model_name=model_name,
            prompt_content=[prompt, img],
            output_format='json'
        )
        return result
