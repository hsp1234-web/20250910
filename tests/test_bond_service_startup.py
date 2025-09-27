# tests/test_bond_service_startup.py

import pytest
import subprocess
import time
import requests
import socket
import sys
from pathlib import Path

# --- Helper to find a free port ---
def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# --- Pytest Fixture to manage the service lifecycle ---
@pytest.fixture(scope="module")
def bond_service():
    """
    一個 Pytest fixture，負責在測試前啟動 bond_data_service，
    並在測試結束後將其關閉。
    此版本經過修改，使用當前的 Python 直譯器，並在測試結束後印出服務日誌。
    """
    python_exec = sys.executable
    service_dir = Path(__file__).resolve().parent.parent / "services" / "bond_data_service"
    port = find_free_port()
    host = "127.0.0.1"
    command = [
        str(python_exec),
        "-m", "uvicorn",
        "main:app",
        "--host", host,
        "--port", str(port),
    ]

    print(f"\n啟動服務指令: {' '.join(command)}")
    # 將 stdout 和 stderr 都捕獲
    process = subprocess.Popen(command, cwd=service_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

    service_url = f"http://{host}:{port}"
    ping_url = f"{service_url}/ping"
    ready = False
    for i in range(40):
        try:
            response = requests.get(ping_url, timeout=0.5)
            if response.status_code == 200:
                print(f"服務在 {ping_url} 上已就緒！")
                ready = True
                break
        except requests.ConnectionError:
            time.sleep(0.5)
        if i % 5 == 0 and i > 0:
            print(f"等待服務啟動中... ({i*0.5}s)")

    if not ready:
        process.terminate()
        stdout, stderr = process.communicate()
        pytest.fail(f"服務在 {service_url} 上啟動超時。\n--- STDOUT ---\n{stdout}\n--- STDERR ---\n{stderr}")

    yield service_url

    # --- 測試結束後的清理工作 ---
    print(f"\n--- 正在關閉服務 (PID: {process.pid}) ---")
    process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=5)
        print("--- 服務日誌 (STDOUT) ---")
        print(stdout)
        if stderr:
            print("\n--- 服務日誌 (STDERR) ---")
            print(stderr)
        print("--- 服務日誌結束 ---")
        print("服務已成功關閉。")
    except subprocess.TimeoutExpired:
        print("關閉超時，強制終止服務。")
        process.kill()
        stdout, stderr = process.communicate()
        print("--- 服務日誌 (STDOUT) on Kill ---")
        print(stdout)
        if stderr:
            print("\n--- 服務日誌 (STDERR) on Kill ---")
            print(stderr)
        print("--- 服務日誌結束 ---")

# --- Test Case ---
@pytest.mark.timeout(30)
def test_ping_endpoint(bond_service):
    print(f"向服務 {bond_service} 的 /ping 端點發送請求...")
    ping_url = f"{bond_service}/ping"
    response = requests.get(ping_url)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "Bond Data Service is running" in data.get("message", "")
    print("Ping 端點測試成功！")

@pytest.mark.skip(reason="此測試已過時，其功能由 test_get_chart_image_endpoint 覆蓋")
def test_get_data_endpoint(bond_service):
    indicator = "gdp"
    data_url = f"{bond_service}/data/{indicator}"
    print(f"向服務 {data_url} 發送請求...")
    response = requests.get(data_url)
    assert response.status_code == 200
    assert "application/json" in response.headers.get("Content-Type", "")
    data = response.json()
    assert isinstance(data, list)
    if data:
        first_item = data[0]
        assert "date" in first_item
        assert "value" in first_item
        print(f"成功驗證了 {len(data)} 筆資料的結構。")
    else:
        print("回應為空列表，這是一個有效的回應。")
    print(f"/data/{indicator} 端點測試成功！")