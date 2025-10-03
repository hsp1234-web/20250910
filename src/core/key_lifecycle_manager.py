# -*- coding: utf-8 -*-
import logging
import threading
import time
import json
from typing import List, Dict, Optional, Literal

# --- 類型定義 ---
KeyStatus = Literal["pending_validation", "valid", "invalid"]

class ApiKey:
    """代表單一 API 金鑰及其狀態的資料類別。"""
    def __init__(self, key_value: str, key_type: str = "gemini"):
        self.key_value = key_value
        self.key_type = key_type
        self.status: KeyStatus = "pending_validation"
        self.last_checked: Optional[float] = None
        self.last_error: Optional[str] = None

    def to_dict(self):
        return {
            # 為了安全，不回傳金鑰本身
            "key_preview": f"...{self.key_value[-4:]}",
            "key_type": self.key_type,
            "status": self.status,
            "last_checked_timestamp": self.last_checked,
            "last_error": self.last_error,
        }

class KeyLifecycleManager:
    """
    一個單例服務，用於在背景管理 API 金鑰的整個生命週期，
    包括從環境變數載入、驗證、狀態更新和自動重試。
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized:
            return

        self.log = logging.getLogger('KeyLifecycleManager')
        self.all_keys: Dict[str, ApiKey] = {}
        self._lock = threading.Lock()
        self._initialized = False
        self.validation_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.RETRY_DELAY_SECONDS = 300  # 5 分鐘

    def load_keys_from_env(self):
        """從環境變數 RAW_API_KEYS 中載入原始金鑰。"""
        import os
        self.log.info("正在從環境變數載入原始 API 金鑰...")
        raw_keys_json = os.environ.get('RAW_API_KEYS')
        if not raw_keys_json:
            self.log.warning("未在環境變數中找到 RAW_API_KEYS，無法載入任何金鑰。")
            return

        try:
            keys_payload = json.loads(raw_keys_json)
            gemini_keys = keys_payload.get("gemini", [])
            fred_key = keys_payload.get("fred")

            with self._lock:
                for key_val in gemini_keys:
                    if key_val and key_val not in self.all_keys:
                        self.all_keys[key_val] = ApiKey(key_value=key_val, key_type="gemini")

                if fred_key and fred_key not in self.all_keys:
                    self.all_keys[fred_key] = ApiKey(key_value=fred_key, key_type="fred")

            self.log.info(f"成功從環境變數載入 {len(self.all_keys)} 個金鑰。")
            self._initialized = True
        except json.JSONDecodeError:
            self.log.error("解析 RAW_API_KEYS 環境變數失敗，內容不是有效的 JSON。")
        except Exception as e:
            self.log.error(f"從環境變數載入金鑰時發生未知錯誤: {e}", exc_info=True)

    def start_validation_loop(self):
        """啟動一個背景執行緒來持續驗證金鑰。"""
        if not self._initialized:
            self.log.error("管理器尚未初始化，無法啟動驗證迴圈。")
            return

        if self.validation_thread and self.validation_thread.is_alive():
            self.log.warning("驗證迴圈已在運行中。")
            return

        self.log.info("正在啟動背景金鑰驗證迴圈...")
        self.stop_event.clear()
        self.validation_thread = threading.Thread(target=self._validation_worker, daemon=True)
        self.validation_thread.start()

    def stop_validation_loop(self):
        """停止背景驗證執行緒。"""
        self.log.info("正在停止背景金鑰驗證迴圈...")
        self.stop_event.set()
        if self.validation_thread:
            self.validation_thread.join(timeout=5)

    def _validate_gemini_key(self, api_key: ApiKey):
        """驗證單一 Gemini API 金鑰。"""
        try:
            # 延遲載入以加速啟動
            import google.generativeai as genai
            from google.api_core import client_options
            from google.api_core.exceptions import GoogleAPICallError

            self.log.info(f"正在驗證 Gemini 金鑰: ...{api_key.key_value[-4:]}")
            # 使用金鑰配置 SDK
            genai.configure(api_key=api_key.key_value, client_options=client_options.ClientOptions(api_endpoint="generativelanguage.googleapis.com"))
            # 嘗試一個輕量級的 API 呼叫來驗證金鑰
            genai.list_models()
            with self._lock:
                api_key.status = "valid"
                api_key.last_error = None
            self.log.info(f"✅ Gemini 金鑰 ...{api_key.key_value[-4:]} 驗證成功。")
        except (GoogleAPICallError, ValueError, Exception) as e:
            error_message = f"Gemini 金鑰驗證失敗: {type(e).__name__}"
            self.log.warning(f"❌ {error_message} (金鑰: ...{api_key.key_value[-4:]})")
            with self._lock:
                api_key.status = "invalid"
                api_key.last_error = error_message
        finally:
            with self._lock:
                api_key.last_checked = time.time()

    def _validate_fred_key(self, api_key: ApiKey):
        """驗證單一 FRED API 金鑰。"""
        try:
            # 延遲載入以加速啟動
            from fredapi import Fred

            self.log.info(f"正在驗證 FRED 金鑰: ...{api_key.key_value[-4:]}")
            fred = Fred(api_key=api_key.key_value)
            # 嘗試一個簡單的請求
            fred.get_series('GNP')
            with self._lock:
                api_key.status = "valid"
                api_key.last_error = None
            self.log.info(f"✅ FRED 金鑰 ...{api_key.key_value[-4:]} 驗證成功。")
        except Exception as e:
            error_message = f"FRED 金鑰驗證失敗: {type(e).__name__}"
            self.log.warning(f"❌ {error_message} (金鑰: ...{api_key.key_value[-4:]})")
            with self._lock:
                api_key.status = "invalid"
                api_key.last_error = str(e)
        finally:
            with self._lock:
                api_key.last_checked = time.time()

    def _validation_worker(self):
        """背景工作者，負責定期驗證金鑰。"""
        self.log.info("✅ 金鑰驗證工作者已啟動。")
        time.sleep(10)  # 初始延遲，等待網路穩定

        validator_map = {
            "gemini": self._validate_gemini_key,
            "fred": self._validate_fred_key,
        }

        while not self.stop_event.is_set():
            keys_to_check = []
            with self._lock:
                current_time = time.time()
                for key_obj in self.all_keys.values():
                    if key_obj.status == "pending_validation":
                        keys_to_check.append(key_obj)
                    elif key_obj.status == "invalid" and \
                         (key_obj.last_checked is None or current_time - key_obj.last_checked > self.RETRY_DELAY_SECONDS):
                        keys_to_check.append(key_obj)

            if keys_to_check:
                self.log.info(f"發現 {len(keys_to_check)} 個金鑰需要驗證/重試。")
                for api_key in keys_to_check:
                    if self.stop_event.is_set(): break

                    validator = validator_map.get(api_key.key_type)
                    if validator:
                        validator(api_key)
                    else:
                        self.log.warning(f"找不到金鑰類型 '{api_key.key_type}' 的驗證器。")

                    time.sleep(2) # 每次驗證之間短暫間隔，避免過於頻繁的請求

            self.stop_event.wait(60) # 每分鐘檢查一次是否有需要重試的金鑰

        self.log.info("金鑰驗證工作者已停止。")

    def get_key_status(self) -> Dict:
        """獲取所有金鑰的當前狀態。"""
        with self._lock:
            return {f"...{key[-4:]}": api_key.to_dict() for key, api_key in self.all_keys.items()}

    def get_valid_gemini_key(self) -> Optional[str]:
        """獲取一個當前有效的 Gemini 金鑰。"""
        with self._lock:
            for key_obj in self.all_keys.values():
                if key_obj.key_type == "gemini" and key_obj.status == "valid":
                    return key_obj.key_value
        return None

    def get_valid_fred_key(self) -> Optional[str]:
        """獲取一個當前有效的 FRED 金鑰。"""
        with self._lock:
            for key_obj in self.all_keys.values():
                if key_obj.key_type == "fred" and key_obj.status == "valid":
                    return key_obj.key_value
        return None

# 創建一個全域單例
key_lifecycle_manager = KeyLifecycleManager()