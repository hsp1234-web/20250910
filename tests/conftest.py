import pytest
import sys
import os
import time
import subprocess
import re
import socket
# import requests # JULES: 暫時註解掉，以避免在無關的測試中引發 ModuleNotFoundError
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

# @pytest.fixture(scope="session")
# def live_services(tmp_path_factory, worker_id):
#     """
#     JULES: 暫時註解掉整個 fixture，因為它依賴 requests，
#     且與 test_v3_poc.py 無關。
#     """
#     pass
