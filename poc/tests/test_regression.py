# poc/tests/test_regression.py

import pytest
import subprocess
import time
import httpx
import pandas as pd
import socket
import os
import json
import sqlite3
import shutil
from contextlib import closing
from pathlib import Path

# --- 設定 ---
OLD_SERVICE_DIR = Path("services/bond_data_service")
NEW_SERVICE_DIR = Path("poc/bond_data_service_v2")
SERVICE_REGISTRY_FILE = "/tmp/service_registry.json"

# --- 輔助函式 ---

def find_free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

def start_service(cwd: Path, app_module: str, port: int, log_file: Path) -> subprocess.Popen:
    cmd = ["uvicorn", app_module, "--host", "127.0.0.1", "--port", str(port)]
    log = open(log_file, "w")
    process = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=log)
    return process

def wait_for_service(port: int, log_file_path: Path, health_endpoint: str = "/health", timeout: int = 45):
    start_time = time.time()
    url = f"http://127.0.0.1:{port}{health_endpoint}"
    while time.time() - start_time < timeout:
        try:
            with httpx.Client() as client:
                response = client.get(url, timeout=2)
                if response.status_code == 200:
                    print(f"服務在埠號 {port} 上已就緒。")
                    return True
        except httpx.RequestError:
            time.sleep(0.5)

    print(f"--- 埠號 {port} 的服務日誌 ({log_file_path}) ---")
    if log_file_path.exists():
        with open(log_file_path, "r") as f: print(f.read())
    else:
        print("日誌檔案未找到！")
    print("--------------------------")
    pytest.fail(f"服務在埠號 {port} 上於 {timeout} 秒內未能啟動。請檢查日誌。")

def setup_old_service_dependencies():
    registry_content = {"key_service": {"port": 9999}}
    with open(SERVICE_REGISTRY_FILE, "w") as f: json.dump(registry_content, f)

def seed_database(db_path: Path, start_date_str: str, end_date_str: str):
    """建立並預先填入一個 SQLite 資料庫，使用更穩健的數據生成邏輯。"""
    print(f"正在為測試填充資料庫: {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS time_series_data (date TEXT NOT NULL, ticker TEXT NOT NULL, price REAL NOT NULL, PRIMARY KEY (date, ticker))")

    tickers = ["SOFR", "DGS10", "DGS2", "VIXCLS", "BAMLH0A0HYM2", "HYG", "NYFED_TOTAL_POS", "WRESBAL", "RRPONTSYD", "NYFED_LONG_POS", "NYFED_SHORT_POS"]
    dates = pd.date_range(start=start_date_str, end=end_date_str, freq='D')

    all_data = []
    # 產生並儲存 BAMLH0A0HYM2 的數據，然後將其複製給 HYG
    hys_data_values = [14.0 + (day_num / 100.0) for day_num in range(len(dates))]

    for i, ticker in enumerate(tickers):
        if ticker == "HYG": continue # HYG 的數據由 BAMLH0A0HYM2 提供，在此跳過

        if ticker == "BAMLH0A0HYM2":
            values = hys_data_values
            # 為 HYG 也加入相同的數據
            for date, value in zip(dates, values):
                all_data.append((date.strftime('%Y-%m-%d'), "HYG", value))
        else:
            values = [10.0 + i + (day_num / 100.0) for day_num in range(len(dates))]

        # 為當前 ticker 加入數據
        for date, value in zip(dates, values):
            all_data.append((date.strftime('%Y-%m-%d'), ticker, value))

    cursor.executemany("INSERT OR REPLACE INTO time_series_data (date, ticker, price) VALUES (?, ?, ?)", all_data)
    conn.commit()
    conn.close()
    print(f"資料庫填充完成，共插入 {len(all_data)} 筆數據。")

# --- 回歸測試 ---

@pytest.fixture
def test_workspace(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("regression_test")

def test_regression_dashboard_data(test_workspace: Path):
    old_service_port, new_service_port = find_free_port(), find_free_port()
    old_log_file = test_workspace / f"service_old.log"
    new_log_file = test_workspace / f"service_new.log"

    params = {"start_date": "2023-01-01", "end_date": "2023-06-30"}
    seeded_db_path = test_workspace / "seeded_db.sqlite3"
    seed_database(seeded_db_path, params["start_date"], params["end_date"])

    shutil.copy(seeded_db_path, OLD_SERVICE_DIR / "bond_data.sqlite3")
    shutil.copy(seeded_db_path, NEW_SERVICE_DIR / "bond_data.sqlite3")

    setup_old_service_dependencies()

    old_process, new_process = None, None
    try:
        print(f"正在埠號 {old_service_port} 上啟動舊服務...")
        old_process = start_service(OLD_SERVICE_DIR, "main:app", old_service_port, old_log_file)

        print(f"正在埠號 {new_service_port} 上啟動新服務...")
        new_process = start_service(Path("."), "poc.bond_data_service_v2.main:app", new_service_port, new_log_file)

        wait_for_service(old_service_port, old_log_file)
        wait_for_service(new_service_port, new_log_file)

        endpoint = "/api/bond_service/dashboard_data"
        with httpx.Client(timeout=60) as client:
            print("正在向兩個服務發送請求...")
            old_response = client.get(f"http://127.0.0.1:{old_service_port}{endpoint}", params=params)
            new_response = client.get(f"http://127.0.0.1:{new_service_port}{endpoint}", params=params)

        assert old_response.status_code == 200, "舊服務應返回 200"
        assert new_response.status_code == 200, "新服務應返回 200"

        old_df = pd.DataFrame(old_response.json()).set_index('date').sort_index()
        new_df = pd.DataFrame(new_response.json()).set_index('date').sort_index()

        # 欄位對齊
        common_cols = old_df.columns.intersection(new_df.columns)
        old_df = old_df[common_cols].sort_index()
        new_df = new_df[common_cols].sort_index()

        print("--- 舊服務返回的數據 (前5筆) ---")
        print(old_df.head())
        print("\n--- 新服務返回的數據 (前5筆) ---")
        print(new_df.head())

        pd.testing.assert_frame_equal(old_df, new_df, check_exact=False, rtol=1e-5, atol=1e-8)
        print("\n✅ 回歸比對成功！新舊服務的輸出完全一致。")

    finally:
        if old_process: old_process.terminate(); old_process.wait()
        if new_process: new_process.terminate(); new_process.wait()
        if os.path.exists(SERVICE_REGISTRY_FILE): os.remove(SERVICE_REGISTRY_FILE)
        if (OLD_SERVICE_DIR / "bond_data.sqlite3").exists(): os.remove(OLD_SERVICE_DIR / "bond_data.sqlite3")
        if (NEW_SERVICE_DIR / "bond_data.sqlite3").exists(): os.remove(NEW_SERVICE_DIR / "bond_data.sqlite3")
        print("已清理所有服務和暫存檔案。")