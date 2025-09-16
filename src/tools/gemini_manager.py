import logging
import json
import time
import sys
import threading
from collections import deque, defaultdict
from pathlib import Path
from typing import List, Optional, Dict, Any

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))

try:
    import google.generativeai as genai
    from google.generativeai.types import GenerationConfig
    from PIL import Image
    # JULES: 匯入 quota_manager 以讀取流量限制
    from db import quota_manager
except ImportError as e:
    logging.warning(f"匯入模組時發生錯誤: {e}。AI 分析功能可能受限。")
    genai = None
    Image = None
    GenerationConfig = None
    quota_manager = None

class ApiKey:
    """一個簡單的類別，用於儲存 API 金鑰及其名稱。"""
    def __init__(self, key_value: str, name: str):
        self.key = key_value
        self.name = name

class GeminiManager:
    """
    管理與 Google Gemini API 的所有互動。
    支援多金鑰輪換、冷卻機制、自動重試機制及主動流量控制。
    """
    def __init__(self, api_keys: List[Dict[str, str]], timeout: int = 180, max_retries: int = 3, cooldown_seconds: int = 60):
        if not genai:
            raise ImportError("GeminiManager 無法初始化，因為 google.generativeai 模組未安裝。")
        if not api_keys:
            raise ValueError("API 金鑰列表不可為空。")
        if not quota_manager:
            raise ImportError("GeminiManager 無法初始化，因為 db.quota_manager 模組無法匯入。")

        self.key_pool = deque([ApiKey(key_value=k['value'], name=k['name']) for k in api_keys])
        self._key_map = {k.key: k for k in self.key_pool}
        self.cooldown_keys: Dict[str, float] = {}
        self.cooldown_seconds = cooldown_seconds

        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()

        # JULES: 新增流量控制相關屬性
        self.quotas: Dict[str, Dict[str, Any]] = self._load_quotas()
        self.request_timestamps: Dict[str, deque] = defaultdict(deque)

        logging.info(f"Gemini 管理器已初始化，共載入 {len(self.key_pool)} 組 API 金鑰。已載入 {len(self.quotas)} 組流量規則。")

    def _load_quotas(self) -> Dict[str, Dict[str, Any]]:
        """從資料庫載入流量限制規則。"""
        try:
            all_quotas = quota_manager.get_all_quotas()
            # 將列表轉換為以 model_name 為鍵的字典，以便快速查詢
            return {q['model_name']: q for q in all_quotas}
        except Exception as e:
            logging.error(f"從資料庫載入流量限制規則時發生錯誤: {e}", exc_info=True)
            return {} # 發生錯誤時返回空字典，避免服務中斷

    def _activate_cooled_down_keys(self):
        """檢查冷卻中的金鑰，並將已到期的移回主金鑰池。"""
        now = time.time()
        for key_value, cooldown_end in list(self.cooldown_keys.items()):
            if now >= cooldown_end:
                del self.cooldown_keys[key_value]
                key_obj = self._key_map.get(key_value)
                if key_obj:
                    self.key_pool.append(key_obj)
                    logging.info(f"金鑰 '{key_obj.name}' 已結束冷卻，返回可用金鑰池。")

    def _enforce_rate_limit(self, model_name: str):
        """
        JULES: 實作流量「安全閥」。
        在發送請求前檢查並執行 RPM (每分鐘請求數) 限制。
        """
        with self._lock:
            # 獲取此模型的流量限制，如果找不到則使用一個較高的預設值
            model_quota = self.quotas.get(model_name)
            if not model_quota:
                logging.warning(f"在資料庫中找不到模型 '{model_name}' 的流量限制規則，將不執行主動限流。")
                return

            rpm_limit = model_quota.get('rpm', 60) # 若規則中無 rpm，預設為 60
            timestamp_deque = self.request_timestamps[model_name]
            now = time.time()

            # 步驟 1: 清理掉所有在一分鐘以前的舊時間戳
            while timestamp_deque and now - timestamp_deque[0] > 60:
                timestamp_deque.popleft()

            # 步驟 2: 檢查目前佇列中的請求數是否已達上限
            if len(timestamp_deque) >= rpm_limit:
                # 計算需要等待的時間
                oldest_timestamp = timestamp_deque[0]
                time_to_wait = 60 - (now - oldest_timestamp)

                if time_to_wait > 0:
                    logging.warning(
                        f"模型 '{model_name}' 已達到 RPM 上限 ({rpm_limit})。將主動暫停 {time_to_wait:.2f} 秒以避免 429 錯誤。"
                    )
                    # 在鎖之外睡眠，避免長時間持有鎖
                    # 但這裡我們需要在鎖內完成所有判斷和操作，所以暫時在鎖內睡眠
                    # 對於高併發場景，這裡可以優化為非同步等待
                    time.sleep(time_to_wait)

            # 步驟 3: 記錄本次請求的時間戳
            timestamp_deque.append(time.time())


    def list_available_models(self) -> List[str]:
        """列出所有支援 'generateContent' 方法的可用 Gemini 模型。"""
        # ... (此函式不涉及高頻率呼叫，暫不加入流量控制) ...
        if not genai: return []
        with self._lock:
            self._activate_cooled_down_keys()
            if not self.key_pool: raise ValueError("金鑰池為空")
            api_key = self.key_pool[0]
        try:
            genai.configure(api_key=api_key.key)
            return [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        except Exception as e:
            logging.error(f"查詢模型時發生錯誤: {e}", exc_info=True)
            raise e

    def _api_call_wrapper(self, task_name: str, model_name: str, prompt_content: List[Any], output_format: str = 'json'):
        if not genai:
            return None, "google.generativeai not installed", "N/A", 0

        # JULES: 在所有操作之前，先執行流量控制檢查
        self._enforce_rate_limit(model_name)

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
                logging.error(f"[{tag}] 設定金鑰時發生錯誤: {e}，跳過此金鑰。", exc_info=True)
                last_error = e
                continue

            generation_config = GenerationConfig(response_mime_type="application/json") if output_format == 'json' else None

            for attempt in range(self.max_retries):
                logging.info(f"[{tag}] 正在執行第 {attempt + 1}/{self.max_retries} 次嘗試...")
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
                    token_usage = response.usage_metadata.total_token_count if hasattr(response, 'usage_metadata') and hasattr(response.usage_metadata, 'total_token_count') else 0

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
                    is_rate_limit_error = any(s in last_error_str for s in ["quota", "resourceexhausted", "429"])

                    if is_rate_limit_error:
                        logging.error(f"[{tag}] 遭遇配額耗盡錯誤。將此金鑰移至冷卻區 {self.cooldown_seconds} 秒。")
                        with self._lock:
                            if api_key in self.key_pool:
                                self.key_pool.remove(api_key)
                                self.cooldown_keys[api_key.key] = time.time() + self.cooldown_seconds
                        break

                    if any(s in last_error_str for s in ["permission_denied", "invalid_api_key", "invalid_argument"]):
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

    def prompt_for_json(self, prompt: str, model_name: str = "gemini-2.0-flash") -> tuple:
        return self._api_call_wrapper(
            task_name="PromptForJson", model_name=model_name,
            prompt_content=[prompt], output_format='json'
        )

    def prompt_for_text(self, prompt: str, model_name: str = "gemini-1.5-pro-latest") -> tuple:
        return self._api_call_wrapper(
            task_name="PromptForText", model_name=model_name,
            prompt_content=[prompt], output_format='text'
        )
