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
    支援多金鑰輪換、冷卻機制和自動重試機制。
    """
    def __init__(self, api_keys: List[Dict[str, str]], timeout: int = 180, max_retries: int = 3, cooldown_seconds: int = 60):
        if not genai:
            raise ImportError("GeminiManager 無法初始化，因為 google.generativeai 模組未安裝。")
        if not api_keys:
            raise ValueError("API 金鑰列表不可為空。")

        self.key_pool = deque([ApiKey(key_value=k['value'], name=k['name']) for k in api_keys])
        self._key_map = {k.key: k for k in self.key_pool} # 預先建立金鑰對應表
        self.cooldown_keys: Dict[str, float] = {}  # key_value -> cooldown_end_timestamp
        self.cooldown_seconds = cooldown_seconds

        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()
        logging.info(f"Gemini 管理器已初始化，共載入 {len(self.key_pool)} 組 API 金鑰。冷卻時間: {cooldown_seconds} 秒。")

    def _activate_cooled_down_keys(self):
        """檢查冷卻中的金鑰，並將已到期的移回主金鑰池。"""
        now = time.time()
        # 使用 list(self.cooldown_keys.items()) 來避免在迭代時修改字典
        for key_value, cooldown_end in list(self.cooldown_keys.items()):
            if now >= cooldown_end:
                # 從冷卻池中移除
                del self.cooldown_keys[key_value]
                # 從預先建立的對應表中尋找 ApiKey 物件
                key_obj = self._key_map.get(key_value)
                if key_obj:
                    self.key_pool.append(key_obj)
                    logging.info(f"金鑰 '{key_obj.name}' 已結束冷卻，返回可用金鑰池。")

    def list_available_models(self) -> List[str]:
        """
        列出所有支援 'generateContent' 方法的可用 Gemini 模型。
        會使用金鑰池中的一個金鑰來進行查詢。
        """
        if not genai:
            logging.warning("無法列出模型，因為 google.generativeai 未安裝。")
            return []

        with self._lock:
            self._activate_cooled_down_keys()
            if not self.key_pool:
                raise ValueError(f"無法列出模型，因為金鑰池是空的 (可能有 {len(self.cooldown_keys)} 個金鑰正在冷卻)。")
            api_key = self.key_pool[0]

        logging.info(f"正在使用金鑰 '{api_key.name}' 查詢可用的模型...")
        try:
            genai.configure(api_key=api_key.key)
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            logging.info(f"查詢成功，找到 {len(available_models)} 個可用模型。")
            return available_models
        except Exception as e:
            logging.error(f"使用金鑰 '{api_key.name}' 查詢模型時發生錯誤: {e}", exc_info=True)
            raise e

    def _api_call_wrapper(self, task_name: str, model_name: str, prompt_content: List[Any], output_format: str = 'json'):
        if not genai:
            return None, "google.generativeai not installed", "N/A"

        last_error = None

        with self._lock:
            self._activate_cooled_down_keys()
            keys_to_try = list(self.key_pool)

        if not keys_to_try:
            error_msg = f"金鑰池為空，無法執行 API 請求。(有 {len(self.cooldown_keys)} 個金鑰正在冷卻中)"
            logging.error(f"[{task_name}] {error_msg}")
            return None, ValueError(error_msg), "N/A", 0

        for i, api_key in enumerate(keys_to_try):
            tag = f"{task_name}-{api_key.name}"
            logging.info(f"[{tag}] 準備使用金鑰 #{i+1}/{len(keys_to_try)} 執行 API 請求...")

            try:
                genai.configure(api_key=api_key.key)
            except Exception as e:
                logging.error(f"[{tag}] 設定金鑰時發生錯誤: {e}，跳過此金鑰。")
                last_error = e
                continue

            generation_config = GenerationConfig(response_mime_type="application/json") if output_format == 'json' else None

            for attempt in range(self.max_retries):
                logging.info(f"[{tag}] 正在執行第 {attempt + 1}/{self.max_retries} 次嘗試 (模型: {model_name}, 格式: {output_format})...")
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

                    with self._lock:
                        if api_key in self.key_pool:
                            self.key_pool.remove(api_key)
                            self.key_pool.append(api_key)

                    logging.info(f"[{tag}] API 請求成功。")
                    # 嘗試獲取 token 使用量，採用更具防禦性的寫法
                    token_usage = 0 # 預設為 0
                    try:
                        if hasattr(response, 'usage_metadata') and response.usage_metadata: # 確保 usage_metadata 存在且不為 None
                            # 優先嘗試直接存取屬性
                            if hasattr(response.usage_metadata, 'total_token_count'):
                                token_usage = response.usage_metadata.total_token_count
                            # 如果是舊版或不同格式，再嘗試 .get() 方法
                            elif hasattr(response.usage_metadata, 'get'):
                                token_usage = response.usage_metadata.get('total_token_count', 0)
                    except Exception as e:
                        logging.warning(f"無法從 usage_metadata 中獲取 token 消耗: {e}")

                    if output_format == 'json':
                        if raw_text.strip().startswith("```json"):
                            raw_text = raw_text.strip()[7:-3].strip()
                        return json.loads(raw_text), None, api_key.name, token_usage
                    else:
                        if raw_text.strip().startswith("```html"):
                            raw_text = raw_text.strip()[7:-3].strip()
                        elif raw_text.strip().startswith("```"):
                            raw_text = raw_text.strip()[3:-3].strip()
                        return raw_text, None, api_key.name, token_usage

                except Exception as e:
                    last_error = e
                    last_error_str = f"{type(e).__name__}: {e}".lower()

                    is_permanent_error = any(s in last_error_str for s in ["permission_denied", "invalid_api_key", "invalid_argument"])
                    is_rate_limit_error = any(s in last_error_str for s in ["quota", "resourceexhausted", "429"])

                    if is_rate_limit_error:
                        logging.error(f"[{tag}] 遭遇配額耗盡錯誤。將此金鑰移至冷卻區 {self.cooldown_seconds} 秒。")
                        with self._lock:
                            if api_key in self.key_pool:
                                self.key_pool.remove(api_key)
                                self.cooldown_keys[api_key.key] = time.time() + self.cooldown_seconds
                        break # 跳出內層重試迴圈，嘗試下一個金鑰

                    if is_permanent_error:
                        logging.error(f"[{tag}] 遭遇永久性錯誤: {last_error_str}。將立即嘗試下一個金鑰。")
                        break

                    if attempt < self.max_retries - 1:
                        wait_time = 2**(attempt + 1)
                        logging.warning(f"[{tag}] 遭遇暫時性錯誤: {last_error_str}，{wait_time} 秒後重試...");
                        time.sleep(wait_time)
                        continue

                    break

        logging.error(f"[{task_name}] 在嘗試了 {len(keys_to_try)} 組金鑰後，API 請求最終失敗。最後一個錯誤: {last_error}")
        return None, last_error, "all_keys_failed", 0

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
        result, _, _ = self._api_call_wrapper(
            task_name="DescribeImage",
            model_name=model_name,
            prompt_content=[prompt, img],
            output_format='json'
        )
        return result
