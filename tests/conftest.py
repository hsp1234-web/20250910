import pytest
import sys
import os
import time
import subprocess
import re
import socket
import requests
from pathlib import Path

# --- 測試環境路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 準備匯入被測試的模組 ---
from db.database import get_db_connection, initialize_database

@pytest.fixture(scope="function")
def db_conn(tmp_path, monkeypatch):
    """
    提供一個乾淨的、初始化的、基於檔案的暫存 SQLite 資料庫。
    這個 fixture 會：
    1. 建立一個暫存資料庫檔案。
    2. 設定 TEST_DB_PATH 環境變數，讓 get_db_connection() 能找到它。
    3. 在此資料庫上執行初始化。
    4. 將連線物件提供給測試。
    5. 在測試結束後自動清理。
    """
    temp_db_path = tmp_path / "test_tasks.db"
    monkeypatch.setenv("TEST_DB_PATH", str(temp_db_path))

    # 現在 get_db_connection() 將會連線到我們的暫存資料庫
    # 我們也將這個連線傳遞給 initialize_database
    conn = get_db_connection()
    assert conn is not None, "無法建立到暫存資料庫的連線"

    initialize_database(conn)

    yield conn

    conn.close()
    # 檢查檔案是否存在，以防連線失敗
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
    啟動一個真實的後端服務 (db_manager, api_server) 以進行 E2E 測試。
    這個 fixture 的 scope 是 'session'，確保服務在整個測試會話中只啟動一次。
    它會使用一個專用的測試資料庫。
    """
    # 為每個測試工作程序建立一個唯一的暫存資料庫，以支援並行測試
    # 如果不是在 xdist 環境中，worker_id 預設為 'master'
    tmp_path = tmp_path_factory.getbasetemp() / worker_id
    tmp_path.mkdir(exist_ok=True)
    test_db_path = tmp_path / "e2e_test.db"

    # --- 環境變數設定 ---
    # 建立一個乾淨的環境變數字典，只包含必要的變數
    # 這可以避免從執行測試的環境中繼承可能產生干擾的變數
    env = os.environ.copy()
    env["TEST_DB_PATH"] = str(test_db_path)
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")

    # --- 初始化資料庫 ---
    # 確保在啟動服務前，測試資料庫已經被初始化
    conn = get_db_connection()
    assert conn is not None, "無法建立到 E2E 測試資料庫的連線"
    initialize_database(conn)
    conn.close()


    # --- 啟動 DB Manager ---
    db_manager_proc = subprocess.Popen(
        [sys.executable, "-m", "db.manager"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        env=env
    )

    # --- 等待 DB Manager 就緒並獲取其埠號 ---
    db_manager_port = None
    db_manager_ready = False
    port_regex = re.compile(r"DB_MANAGER_PORT: (\d+)")
    ready_regex = re.compile(r"DB_MANAGER_READY")

    # 增加一個超時機制
    start_time = time.time()
    for line in iter(db_manager_proc.stdout.readline, ''):
        if time.time() - start_time > 20: # 20秒超時
            db_manager_proc.terminate()
            pytest.fail("等待 DB Manager 就緒超時。")

        print(f"[db_manager_fixture] {line.strip()}") # 在測試輸出中顯示日誌
        if not db_manager_port:
            port_match = port_regex.search(line)
            if port_match:
                db_manager_port = int(port_match.group(1))

        if not db_manager_ready:
            ready_match = ready_regex.search(line)
            if ready_match:
                db_manager_ready = True

        if db_manager_port and db_manager_ready:
            print("DB Manager 已回報埠號並已就緒。")
            break

    if not db_manager_port or not db_manager_ready:
        db_manager_proc.terminate()
        pytest.fail("無法在 DB Manager 啟動日誌中找到埠號和就緒信號。")

    env["DB_MANAGER_PORT"] = str(db_manager_port)

    # --- 啟動 API Server ---
    api_port = find_free_port()
    api_base_url = f"http://127.0.0.1:{api_port}"
    api_server_proc = subprocess.Popen(
        [sys.executable, "-m", "api.api_server", "--port", str(api_port)],
        # stdout=subprocess.PIPE, # 註解掉以便直接在主控台看到輸出
        # stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        env=env
    )

    # --- 等待 API Server 就緒 ---
    # 使用 requests 輪詢健康檢查端點
    ready = False
    # 增加超時時間，以應對啟動緩慢的情況
    for _ in range(450): # ~45 秒超時
        try:
            # 健康檢查端點現在是 /api/health
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

    # --- 提供服務資訊給測試 ---
    yield {"base_url": api_base_url, "db_path": str(test_db_path)}

    # --- 測試會話結束後的清理 ---
    print("\n--- 正在關閉後端服務 ---")
    api_server_proc.terminate()
    db_manager_proc.terminate()
    api_server_proc.wait(timeout=5)
    db_manager_proc.wait(timeout=5)
    print("--- 後端服務已關閉 ---")
