import pytest
import sys
import os
import time
import subprocess
import re
import socket
import requests
from pathlib import Path

# --- 準備匯入被測試的模組 ---
# pytest 現在會透過 pyproject.toml 自動處理 sys.path
from db.database import get_db_connection, initialize_database

# 修正：定義 SRC_DIR
SRC_DIR = Path(__file__).parent.parent / "src"

@pytest.fixture(scope="function")
def db_conn(tmp_path, monkeypatch):
    """
    提供一個乾淨的、初始化的、基於檔案的暫存 SQLite 資料庫。
    """
    temp_db_path = tmp_path / "test_tasks.db"
    monkeypatch.setenv("TEST_DB_PATH", str(temp_db_path))
    conn = get_db_connection()
    assert conn is not None, "無法建立到暫存資料庫的連線"
    initialize_database(conn)
    yield conn
    conn.close()
    if temp_db_path.exists():
        os.remove(temp_db_path)

def find_free_port():
    """找到一個可用的埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

@pytest.fixture(scope="session")
def live_services(tmp_path_factory, worker_id):
    """
    啟動一個真實的後端服務以進行 E2E 測試。
    """
    tmp_path = tmp_path_factory.getbasetemp() / worker_id
    tmp_path.mkdir(exist_ok=True)
    test_db_path = tmp_path / "e2e_test.db"

    env = os.environ.copy()
    env["TEST_DB_PATH"] = str(test_db_path)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    conn = get_db_connection()
    assert conn is not None, "無法建立到 E2E 測試資料庫的連線"
    initialize_database(conn)
    conn.close()

    db_manager_proc = subprocess.Popen(
        [sys.executable, "-m", "db.manager"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        env=env
    )

    db_manager_port = None
    db_manager_ready = False
    port_regex = re.compile(r"DB_MANAGER_PORT: (\d+)")
    ready_regex = re.compile(r"DB_MANAGER_READY")
    start_time = time.time()

    for line in iter(db_manager_proc.stdout.readline, ''):
        if time.time() - start_time > 20:
            db_manager_proc.terminate()
            pytest.fail("等待 DB Manager 就緒超時。")
        print(f"[db_manager_fixture] {line.strip()}")
        if not db_manager_port:
            port_match = port_regex.search(line)
            if port_match:
                db_manager_port = int(port_match.group(1))
        if not db_manager_ready:
            ready_match = ready_regex.search(line)
            if ready_match:
                db_manager_ready = True
        if db_manager_port and db_manager_ready:
            break

    if not db_manager_port or not db_manager_ready:
        db_manager_proc.terminate()
        pytest.fail("無法在 DB Manager 啟動日誌中找到埠號和就緒信號。")

    env["DB_MANAGER_PORT"] = str(db_manager_port)

    api_port = find_free_port()
    api_base_url = f"http://127.0.0.1:{api_port}"
    api_server_proc = subprocess.Popen(
        [sys.executable, "-m", "api.api_server", "--port", str(api_port)],
        text=True,
        encoding='utf-8',
        env=env
    )

    ready = False
    for _ in range(450):
        try:
            response = requests.get(f"{api_base_url}/api/health", timeout=0.1)
            if response.status_code == 200:
                print("API Server 已就緒！")
                ready = True
                break
        except requests.ConnectionError:
            pass
        time.sleep(0.1)

    if not ready:
        db_manager_proc.terminate()
        api_server_proc.terminate()
        pytest.fail("API Server 未能在指定時間內啟動。")

    yield {"base_url": api_base_url, "db_path": str(test_db_path)}

    print("\n--- 正在關閉後端服務 ---")
    api_server_proc.terminate()
    db_manager_proc.terminate()
    api_server_proc.wait(timeout=5)
    db_manager_proc.wait(timeout=5)
    print("--- 後端服務已關閉 ---")