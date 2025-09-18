# src/core/managers/readiness_manager.py
import logging
import threading
import requests
from pathlib import Path

log = logging.getLogger('readiness_manager')

class ReadinessManager:
    """
    負責在核心服務啟動後，執行後續的準備工作，
    如觸發金鑰驗證，並最終發布「完全就緒」信號。
    """

    def __init__(self, api_port: int, api_ready_event: threading.Event):
        if not api_port or not isinstance(api_ready_event, threading.Event):
            raise ValueError("必須提供有效的 API 埠號和就緒事件。")
        self.api_port = api_port
        self.api_ready_event = api_ready_event
        self.readiness_signal_file = Path("/tmp/full_ready.signal")

    def _trigger_key_validation(self):
        """觸發背景金鑰驗證。"""
        validation_url = f"http://127.0.0.1:{self.api_port}/api/keys/validate"
        log.info(f"[核心準備] 正在向 {validation_url} 發送 POST 請求以觸發背景驗證...")
        try:
            # 使用較短的超時，因為我們只是在觸發一個背景任務
            response = requests.post(validation_url, timeout=15)
            log.info(f"[核心準備] 金鑰驗證觸發完成，狀態碼: {response.status_code}")
            if response.status_code != 200:
                log.warning(f"[核心準備] 觸發金鑰驗證時，伺服器回應非預期: {response.text[:200]}")
        except requests.exceptions.RequestException as req_e:
            # 觸發失敗不是致命錯誤，因為我們有懶驗證作為備援
            log.warning(f"[核心準備] 發送背景驗證請求時發生網路層錯誤: {req_e}。懶驗證機制將作為備援。")

    def _signal_full_readiness(self):
        """發送「完全就緒」信號。"""
        log.info("✅ [核心準備] 核心服務準備完畢！發送『完全就緒』信號。")
        # 建立檔案信號供 api_server 檢查
        try:
            self.readiness_signal_file.touch()
        except Exception as e:
            log.error(f"建立就緒信號檔案 '{self.readiness_signal_file}' 時失敗: {e}")

    def run_in_background(self):
        """
        在背景執行緒中執行的主函式。
        """
        try:
            log.info("[核心準備] 背景任務已啟動，等待 API 伺服器就緒...")

            server_is_ready = self.api_ready_event.wait(timeout=60)

            if not server_is_ready:
                log.error("[核心準備] 等待 API 伺服器就緒超時，無法觸發金鑰驗證。")
                return

            log.info("[核心準備] API 伺服器已就緒。")

            self._trigger_key_validation()

            self._signal_full_readiness()

        except Exception as e:
            log.critical(f"❌ [核心準備] 背景任務發生致命錯誤: {e}", exc_info=True)
            # 即使失敗，也嘗試發出信號，讓前端知道發生了問題，而不是無限期等待
            if not self.readiness_signal_file.exists():
                 self.readiness_signal_file.write_text(f"Error: {e}", encoding="utf-8")
