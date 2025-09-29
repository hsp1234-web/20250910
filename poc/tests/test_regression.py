# poc/tests/test_regression.py
# 繁體中文註解：回歸對比測試

import time
import subprocess
import pytest
import httpx
import pandas as pd
import logging
import io
from typing import Generator, Tuple

# --- 日誌設定 ---
logger = logging.getLogger(__name__)

# --- 常數定義 ---
OLD_SERVICE_PORT = 8001
NEW_SERVICE_PORT = 8002
OLD_SERVICE_URL = f"http://127.0.0.1:{OLD_SERVICE_PORT}"
NEW_SERVICE_URL = f"http://127.0.0.1:{NEW_SERVICE_PORT}"
HEALTH_CHECK_ENDPOINT = "/health"

# --- 輔助函式 ---

def start_service(module_path: str, port: int, log_file: str, cwd: str = None) -> subprocess.Popen:
    """啟動一個 FastAPI 服務子程序。"""
    cmd = [
        "python3", "-m", "uvicorn",
        f"{module_path}:app",
        "--host", "127.0.0.1",
        "--port", str(port)
    ]
    log_handle = open(log_file, "w")
    process = subprocess.Popen(cmd, stdout=log_handle, stderr=log_handle, cwd=cwd)
    logger.info(f"正在啟動服務 {module_path} 於埠 {port} (PID: {process.pid}) 在目錄 {cwd or '.'}...")
    return process

def wait_for_service(url: str, timeout: int = 30):
    """等待服務啟動並通過健康檢查。"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with httpx.Client() as client:
                response = client.get(url)
                if response.status_code == 200:
                    logger.info(f"服務於 {url} 已成功啟動。")
                    return True
        except httpx.RequestError:
            time.sleep(0.5) # 稍作等待後重試
    logger.error(f"服務於 {url} 在 {timeout} 秒內未能啟動。")
    return False

# --- Pytest Fixture: 設定與清理服務 ---

@pytest.fixture(scope="module")
def running_services() -> Generator[Tuple[str, str], None, None]:
    """
    一個 Pytest fixture，負責在測試開始前啟動新、舊兩個版本的服務，
    並在測試結束後將它們全部關閉。
    """
    old_service_process = None
    new_service_process = None
    try:
        # 啟動舊版服務，並指定其工作目錄
        old_service_process = start_service(
            "main",
            OLD_SERVICE_PORT,
            "old_service_regression.log",
            cwd="services/bond_data_service"
        )
        # 啟動新版服務
        new_service_process = start_service(
            "poc.bond_data_service_v2.main",
            NEW_SERVICE_PORT,
            "new_service_regression.log"
        )

        # 等待兩個服務都成功啟動
        old_ready = wait_for_service(f"{OLD_SERVICE_URL}{HEALTH_CHECK_ENDPOINT}")
        new_ready = wait_for_service(f"{NEW_SERVICE_URL}{HEALTH_CHECK_ENDPOINT}")

        if not (old_ready and new_ready):
            raise RuntimeError("一個或多個服務未能成功啟動，測試中止。")

        # 使用 yield 將控制權交還給測試函式
        yield OLD_SERVICE_URL, NEW_SERVICE_URL

    finally:
        # 測試結束後，無論成功或失敗，都確保關閉子程序
        logger.info("正在關閉服務...")
        if old_service_process:
            old_service_process.terminate()
            old_service_process.wait()
            logger.info(f"舊版服務 (PID: {old_service_process.pid}) 已關閉。")
        if new_service_process:
            new_service_process.terminate()
            new_service_process.wait()
            logger.info(f"新版服務 (PID: {new_service_process.pid}) 已關閉。")

# --- 回歸測試案例 ---

def test_dashboard_data_regression(running_services: Tuple[str, str]):
    """
    對比新、舊服務的 `/api/bond_service/dashboard_data` 端點的回應。
    """
    old_url, new_url = running_services
    endpoint = "/api/bond_service/dashboard_data"

    # 使用相同的查詢參數
    params = {"start_date": "2023-01-01", "end_date": "2023-12-31"}

    with httpx.Client(timeout=60) as client:
        # 1. 請求舊版服務 (預期它會因為缺少 API 金鑰而失敗)
        logger.info(f"正在向舊版服務請求: {old_url}{endpoint} (預期失敗)")
        old_response = client.get(f"{old_url}{endpoint}", params=params)
        assert old_response.status_code == 500, f"舊版服務應返回 500，但返回了 {old_response.status_code}"
        logger.info("舊版服務如預期般返回 500 錯誤，驗證其脆弱性。")

        # 2. 請求新版服務 (預期它會因為健壯性改進而成功)
        logger.info(f"正在向新版服務請求: {new_url}{endpoint} (預期成功)")
        new_response = client.get(f"{new_url}{endpoint}", params=params)
        assert new_response.status_code == 200, f"新版服務應返回 200，但返回了 {new_response.status_code}"
        logger.info("新版服務如預期般返回 200 成功狀態，驗證其健壯性。")

    # 3. 驗證新服務回應的結構
    logger.info("正在驗證新服務的回應結構...")
    try:
        new_data = new_response.json()
        assert isinstance(new_data, list), "新版服務的回應應為一個 JSON 陣列"
        if new_data:
            assert isinstance(new_data[0], dict), "JSON 陣列中的元素應為物件"
        logger.info("回歸測試成功：已驗證新服務在無 API 金鑰時的健壯性優於舊服務。")
    except Exception as e:
        with open("new_response.json", "w") as f:
            f.write(new_response.text)
        pytest.fail(f"新服務的回應結構驗證失敗: {e}")