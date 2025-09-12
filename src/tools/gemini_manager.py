import logging
import json
import time
import threading
from collections import deque
from typing import List, Optional, Dict, Any

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    from PIL import Image
except ImportError:
    logging.warning("google-generativeai or pillow not found. AI analysis will be disabled.")
    genai = None
    Image = None
    GenerationConfig = None

class ApiKey:
    """一個簡單的類別，用於儲存 API 金鑰及其名稱。"""
    def __init__(self, key_value: str, name: str):
        self.key = key_value
        self.name = name

class GeminiManager:
    """
    管理與 Google Gemini API 的所有互動。
    支援多金鑰輪換和自動重試機制。
    """
    def __init__(self, api_keys: List[Dict[str, str]], timeout: int = 180, max_retries: int = 3):
        if not genai:
            raise ImportError("GeminiManager 無法初始化，因為 google.generativeai 模組未安裝。")
        if not api_keys:
            raise ValueError("API 金鑰列表不可為空。")
        self.key_pool = deque([ApiKey(key_value=k['value'], name=k['name']) for k in api_keys])
        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()
        logging.info(f"Gemini 管理器已初始化，共載入 {len(self.key_pool)} 組 API 金鑰。")

    def _get_key(self) -> ApiKey:
        with self._lock:
            key = self.key_pool[0]
            self.key_pool.rotate(-1)
            return key

    def _api_call_wrapper(self, task_name: str, model_name: str, prompt_content: List[Any], output_format: str = 'json'):
        if not genai:
            return None, None, "google.generativeai not installed", "N/A"

        api_key = self._get_key()
        last_error = None
        usage_metadata = None

        generation_config = GenerationConfig(response_mime_type="application/json") if output_format == 'json' else None

        for attempt in range(self.max_retries):
            tag = f"{task_name}-{api_key.name}"
            logging.info(f"[{tag}] 正在執行 API 請求 (模型: {model_name}, 格式: {output_format}, 第 {attempt + 1}/{self.max_retries} 次)...")
            try:
                genai.configure(api_key=api_key.key)
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(
                    prompt_content,
                    generation_config=generation_config,
                    request_options={'timeout': self.timeout}
                )

                # 提取元數據
                try:
                    usage_metadata = response.usage_metadata
                except Exception:
                    usage_metadata = None # 如果沒有元數據，則忽略

                raw_text = response.text
                if not raw_text:
                    raise ValueError("API 回傳空內容")

                if output_format == 'json':
                    if raw_text.strip().startswith("```json"):
                        raw_text = raw_text.strip()[7:-3].strip()
                    return json.loads(raw_text), usage_metadata, None, api_key.name
                else:  # output_format == 'text'
                    # 清理常見的 Markdown 程式碼區塊
                    if raw_text.strip().startswith("```html"):
                        raw_text = raw_text.strip()[7:-3].strip()
                    elif raw_text.strip().startswith("```"):
                        # 通用移除 ```
                        raw_text = raw_text.strip()[3:-3].strip()
                    return raw_text, usage_metadata, None, api_key.name

            except Exception as e:
                last_error = e
                last_error_str = f"{type(e).__name__}: {e}"
                if any(s in last_error_str.lower() for s in ["500", "503", "timed out", "deadline", "aborted", "reset", "quota"]) and attempt < self.max_retries - 1:
                    logging.warning(f"[{tag}] 請求失敗 (可重試)，{2**(attempt+1)} 秒後重試...");
                    time.sleep(2**(attempt+1))
                    continue
                break

        logging.error(f"[{tag}] 經過 {self.max_retries} 次嘗試後，API 請求最終失敗: {last_error}")
        return None, usage_metadata, last_error, api_key.name

    def prompt_for_json(self, prompt: str, model_name: str = "gemini-1.5-flash-latest") -> (Optional[Dict], Any, str):
        """
        使用自訂提示詞執行請求，並期望回傳一個 JSON 物件。
        適用於第一階段的結構化資料提取。
        回傳 (結果, 使用元數據, 錯誤, 使用的金鑰名稱)
        """
        result, usage_metadata, err, key_name = self._api_call_wrapper(
            task_name="PromptForJson",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='json'
        )
        if err:
            raise err
        return result, usage_metadata, key_name


    def prompt_for_text(self, prompt: str, model_name: str = "gemini-1.5-pro-latest") -> (Optional[str], Any, str):
        """
        使用自訂提示詞執行請求，並期望回傳純文字 (例如 HTML)。
        適用於第二階段的報告生成。
        回傳 (結果, 使用元數據, 錯誤, 使用的金鑰名稱)
        """
        result, usage_metadata, err, key_name = self._api_call_wrapper(
            task_name="PromptForText",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='text'
        )
        if err:
            raise err
        return result, usage_metadata, key_name

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
        result, _, _ = self._api_call_wrapper(
            task_name="DescribeImage",
            model_name=model_name,
            prompt_content=[prompt, img],
            output_format='json'
        )
        return result
