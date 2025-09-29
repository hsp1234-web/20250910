# poc/tests/test_new_service_alone.py
# 繁體中文註解：新服務獨立啟動測試

import time
import subprocess
import pytest
import httpx
import logging
from typing import Generator

# --- 日誌設定 ---
logger = logging.getLogger(__name__)

# --- 常數定義 ---
NEW_SERVICE_PORT = 8002
NEW_SERVICE_URL = f"http://127.0.0.1:{NEW_SERVICE_PORT}"
HEALTH_CHECK_ENDPOINT = "/health"
LOG_FILE = "new_service_alone.log"

# --- Pytest Fixture ---

@pytest.fixture(scope="module")
def running_new_service() -> Generator[str, None, None]:
    """
    一個 Pytest fixture，只負責啟動新服務，並在測試結束後關閉它。
    """
    service_process = None
    log_handle = open(LOG_FILE, "w")
    try:
        # 啟動新版服務
        cmd = [
            "python3", "-m", "uvicorn",
            "poc.bond_data_service_v2.main:app",
            "--host", "127.0.0.1",
            "--port", str(NEW_SERVICE_PORT)
        ]
        service_process = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle)
        logger.info(f"正在啟動新服務於埠 {NEW_SERVICE_PORT} (PID: {service_process.pid})...")

        # 等待服務啟動
        start_time = time.time()
        is_ready = False
        while time.time() - start_time < 30: # 30 秒超時
            try:
                with httpx.Client() as client:
                    response = client.get(f"{NEW_SERVICE_URL}{HEALTH_CHECK_ENDPOINT}")
                    if response.status_code == 200:
                        logger.info(f"新服務於 {NEW_SERVICE_URL} 已成功啟動。")
                        is_ready = True
                        break
            except httpx.RequestError:
                time.sleep(0.5)

        if not is_ready:
            raise RuntimeError(f"新服務在30秒內未能啟動。請檢查日誌檔案 '{LOG_FILE}'。")

        yield NEW_SERVICE_URL

    finally:
        # 清理
        logger.info("正在關閉新服務...")
        if service_process:
            service_process.terminate()
            service_process.wait()
            logger.info(f"新服務 (PID: {service_process.pid}) 已關閉。")
        log_handle.close()

# --- 測試案例 ---

def test_new_service_health_check(running_new_service: str):
    """
    一個極簡的測試，只驗證新服務的 /health 端點是否返回 200 OK。
    """
    url = running_new_service
    with httpx.Client() as client:
        response = client.get(f"{url}{HEALTH_CHECK_ENDPOINT}")
        assert response.status_code == 200
    logger.info("獨立啟動測試成功：新服務的 /health 端點可正常訪問。")

def test_dashboard_endpoint_in_isolation(running_new_service: str):
    """
    在隔離環境中測試儀表板數據端點，以觸發執行階段的錯誤。
    """
    url = running_new_service
    endpoint = "/api/bond_service/dashboard_data"
    params = {"start_date": "2023-01-01", "end_date": "2023-12-31"}

    logger.info(f"正在隔離環境中測試端點: {url}{endpoint}...")
    with httpx.Client(timeout=60) as client:
        response = client.get(f"{url}{endpoint}", params=params)
        # 我們預期這會失敗，但這是為了獲取日誌
        assert response.status_code == 200, f"儀表板端點應返回 200，但返回了 {response.status_code}"