# tests/test_bond_service_startup.py

import pytest
import subprocess
import time
import requests
import socket
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
    """
    service_dir = Path(__file__).resolve().parent.parent / "services" / "bond_data_service"
    python_exec = service_dir / ".venv" / "bin" / "python"

    if not python_exec.exists():
        pytest.fail(f"找不到虛擬環境的 Python 直譯器: {python_exec}")

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

    # 在服務的目錄下啟動，以便 uvicorn 找到 main:app
    process = subprocess.Popen(command, cwd=service_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

    # --- 等待服務就緒 ---
    service_url = f"http://{host}:{port}"
    ping_url = f"{service_url}/ping"
    ready = False
    for _ in range(20):  # 等待最多 10 秒
        try:
            response = requests.get(ping_url, timeout=0.5)
            if response.status_code == 200:
                print(f"服務在 {ping_url} 上已就緒！")
                ready = True
                break
        except requests.ConnectionError:
            time.sleep(0.5)

    if not ready:
        process.terminate()
        process.wait()
        pytest.fail(f"服務在 {service_url} 上啟動超時。\n日誌:\n{process.stdout.read()}")

    # yield 將控制權交給測試函式
    yield service_url

    # --- 測試結束後的清理工作 ---
    print(f"\n正在關閉服務 (PID: {process.pid})...")
    process.terminate()
    try:
        process.wait(timeout=5)
        print("服務已成功關閉。")
    except subprocess.TimeoutExpired:
        print("關閉超時，強制終止服務。")
        process.kill()
        process.wait()

# --- Test Case ---
@pytest.mark.timeout(120)
def test_ping_endpoint(bond_service):
    """
    測試 bond_data_service 的 /ping 健康檢查端點。
    """
    print(f"向服務 {bond_service} 的 /ping 端點發送請求...")

    # 從 fixture 獲取服務 URL
    ping_url = f"{bond_service}/ping"

    response = requests.get(ping_url)

    # 驗證狀態碼
    assert response.status_code == 200, f"預期狀態碼為 200，但收到 {response.status_code}"

    # 驗證回應內容
    data = response.json()
    assert data["status"] == "ok", f"預期狀態為 'ok'，但收到 '{data.get('status')}'"
    assert "Bond Data Service is running" in data.get("message", ""), "回應訊息不符合預期"

    print("Ping 端點測試成功！")


def test_get_data_endpoint(bond_service):
    """
    測試 /data/{indicator} 端點，確保它能返回正確格式的資料。
    """
    indicator = "gdp"
    data_url = f"{bond_service}/data/{indicator}"
    print(f"向服務 {data_url} 發送請求...")

    response = requests.get(data_url)

    # 1. 驗證狀態碼
    assert response.status_code == 200, f"預期狀態碼為 200，但收到 {response.status_code}"

    # 2. 驗證回應標頭
    assert "application/json" in response.headers.get("Content-Type", ""), "回應的 Content-Type 應為 application/json"

    # 3. 驗證回應內容
    data = response.json()
    assert isinstance(data, list), f"預期回應是一個列表，但收到 {type(data)}"

    # 4. (可選) 如果有資料，驗證資料結構
    if data:
        first_item = data[0]
        assert "date" in first_item, "資料項目中應包含 'date' 鍵"
        assert "value" in first_item, "資料項目中應包含 'value' 鍵"
        print(f"成功驗證了 {len(data)} 筆資料的結構。")
    else:
        print("回應為空列表，這是一個有效的回應。")

    print(f"/data/{indicator} 端點測試成功！")
