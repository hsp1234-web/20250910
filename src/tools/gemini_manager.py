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

    def _api_call_wrapper(self, task_name: str, model_name: str, prompt_content: List[Any], output_format: str = 'json'):
        if not genai:
            return None, "google.generativeai not installed", "N/A"

        last_error = None

        # 獲取當前金鑰池的快照進行本次操作，並確保執行緒安全
        with self._lock:
            keys_to_try = list(self.key_pool)

        if not keys_to_try:
            logging.error(f"[{task_name}] 金鑰池為空，無法執行 API 請求。")
            return None, ValueError("金鑰池為空"), "N/A"

        # 外層迴圈：遍歷所有可用的金鑰 (實現故障轉移)
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

            # 內層迴圈：使用單一金鑰進行重試 (應對暫時性錯誤)
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

                    # --- 成功處理 ---
                    # 將剛用過的有效金鑰輪換到隊伍末端，以實現負載均衡
                    with self._lock:
                        try:
                            # 為了執行緒安全，我們只在確定 key 存在時才操作
                            self.key_pool.remove(api_key)
                            self.key_pool.append(api_key)
                        except ValueError:
                            # 如果在多執行緒環境下，key 已被其他執行緒移除，則忽略
                            logging.warning(f"[{tag}] 在輪換金鑰時，找不到 key，可能已被其他執行緒處理。")

                    logging.info(f"[{tag}] API 請求成功。")
                    if output_format == 'json':
                        if raw_text.strip().startswith("```json"):
                            raw_text = raw_text.strip()[7:-3].strip()
                        return json.loads(raw_text), None, api_key.name
                    else:  # output_format == 'text'
                        if raw_text.strip().startswith("```html"):
                            raw_text = raw_text.strip()[7:-3].strip()
                        elif raw_text.strip().startswith("```"):
                            raw_text = raw_text.strip()[3:-3].strip()
                        return raw_text, None, api_key.name

                except Exception as e:
                    last_error = e
                    last_error_str = f"{type(e).__name__}: {e}"

                    # 檢查是否為永久性錯誤 (例如配額)，若是，則直接跳出內層迴圈換下一個金鑰
                    if any(s in last_error_str.lower() for s in ["quota", "permission_denied", "invalid_api_key", "invalid_argument"]):
                        logging.error(f"[{tag}] 遭遇永久性錯誤: {last_error_str}。將立即嘗試下一個金鑰。")
                        break # 跳出內層重試迴圈

                    # 檢查是否為暫時性錯誤
                    if any(s in last_error_str.lower() for s in ["500", "503", "timed out", "deadline", "aborted", "reset"]) and attempt < self.max_retries - 1:
                        wait_time = 2**(attempt + 1)
                        logging.warning(f"[{tag}] 遭遇暫時性錯誤，{wait_time} 秒後重試...");
                        time.sleep(wait_time)
                        continue # 繼續內層重試迴圈

                    # 如果是其他未知錯誤，或已達最大重試次數，也跳出內層迴圈
                    break

            # 如果內層迴圈是因為 break 而結束 (而不是 return)，我們會繼續外層迴圈嘗試下一個金鑰
            # 如果內層迴圈是因為成功 (return) 而結束，則此處不會被執行

        # 如果遍歷完所有金鑰後仍然失敗
        logging.error(f"[{task_name}] 在嘗試了 {len(keys_to_try)} 組金鑰後，API 請求最終失敗。最後一個錯誤: {last_error}")
        return None, last_error, "all_keys_failed"

    def prompt_for_json(self, prompt: str, model_name: str = "gemini-2.0-flash") -> Optional[Dict]:
        """
        使用自訂提示詞執行請求，並期望回傳一個 JSON 物件。
        適用於第一階段的結構化資料提取。
        """
        result, _, _ = self._api_call_wrapper(
            task_name="PromptForJson",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='json'
        )
        return result

    def prompt_for_text(self, prompt: str, model_name: str = "gemini-1.5-pro-latest") -> Optional[str]:
        """
        使用自訂提示詞執行請求，並期望回傳純文字 (例如 HTML)。
        適用於第二階段的報告生成。
        """
        result, _, _ = self._api_call_wrapper(
            task_name="PromptForText",
            model_name=model_name,
            prompt_content=[prompt],
            output_format='text'
        )
        return result

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
