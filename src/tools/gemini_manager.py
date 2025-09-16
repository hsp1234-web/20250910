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
    # POC V3: 匯入新的金鑰健康管理器
    from core import key_health_manager
except ImportError as e:
    logging.warning(f"匯入模組時發生錯誤: {e}。AI 分析功能可能受限。")
    genai = None
    Image = None
    GenerationConfig = None
    key_health_manager = None

class ApiKey:
    """一個簡單的類別，用於儲存 API 金鑰及其名稱和雜湊值。"""
    def __init__(self, key_value: str, name: str, key_hash: str):
        self.key = key_value
        self.name = name
        self.hash = key_hash

class GeminiManager:
    """
    管理與 Google Gemini API 的所有互動。
    支援多金鑰輪換、冷卻機制、自動重試機制及主動流量控制。
    """
    def __init__(self, api_keys: List[Dict[str, str]], timeout: int = 180, max_retries: int = 3, cooldown_seconds: int = 60):
        # JULES: 移除對 genai 模組的檢查，以提高在 mock 環境下的可測試性。
        # if not genai:
        #     raise ImportError("GeminiManager 無法初始化，因為 google.generativeai 模組未安裝。")
        if not api_keys:
            raise ValueError("API 金鑰列表不可為空。")
        # JULES: 移除對 quota_manager 的依賴檢查
        if not key_health_manager:
            logging.warning("key_health_manager 模組無法匯入，V3 健康管理功能將被停用。")


        self.key_pool = deque([ApiKey(key_value=k['value'], name=k['name'], key_hash=k['hash']) for k in api_keys])
        self._key_map = {k.key: k for k in self.key_pool}
        self.cooldown_keys: Dict[str, float] = {}
        self.cooldown_seconds = cooldown_seconds

        self.timeout = timeout
        self.max_retries = max_retries
        self._lock = threading.Lock()

        # JULES: 移除舊的流量控制屬性
        # self.quotas: Dict[str, Dict[str, Any]] = self._load_quotas()
        self.request_timestamps: Dict[str, deque] = defaultdict(deque)

        logging.info(f"Gemini 管理器已初始化，共載入 {len(self.key_pool)} 組 API 金鑰。")

# JULES: 移除整個 _load_quotas 函式，因其已不再需要

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
        POC 階段：此功能暫時停用，因為全域 RPM 限制不是本次 POC 的驗證範圍。
        """
        pass


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
                    # POC V3: 回報金鑰使用成功
                    if key_health_manager:
                        key_health_manager.record_key_success(api_key.hash)

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
                        # POC V3: 回報金鑰使用失敗
                        if key_health_manager:
                            key_health_manager.record_key_error(api_key.hash)

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
