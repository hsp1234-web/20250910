# tests/test_key_service.py
import subprocess
import sys
import time
import shutil
from pathlib import Path
import pytest
import requests
import os

# --- 常數定義 ---
# 獲取專案根目錄 (tests/../)
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVICE_DIR = ROOT_DIR / "services" / "key_service"
VENV_DIR = SERVICE_DIR / ".test_venv"
PYTHON_EXEC = VENV_DIR / "bin" / "python"
REQ_FILE = SERVICE_DIR / "requirements.txt"
MAIN_SCRIPT = SERVICE_DIR / "main.py"
def find_free_port():
    """使用 socket 尋找一個可用的埠號。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# 動態設定埠號
def find_free_port():
    """使用 socket 尋找一個可用的埠號。"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

# --- Pytest Fixture: 設定與拆卸測試環境 ---

@pytest.fixture(scope="module")
def key_service_environment():
    """
    一個 Module 等級的 fixture，負責：
    1. (Setup) 建立一個乾淨的、獨立的虛擬環境並安裝依賴。
    2. (Setup) 在該環境中啟動 key_service 服務。
    3. (Yield) 將服務的 URL 提供給測試函式使用。
    4. (Teardown) 測試結束後，終止服務並刪除整個虛擬環境。
    """
    # --- Setup ---
    service_port = find_free_port()
    health_check_url = f"http://127.0.0.1:{service_port}/"
    base_api_url = f"http://127.0.0.1:{service_port}"

    # 1. 清理並建立虛擬環境
    print(f"\n[Setup] 正在於 {VENV_DIR} 建立測試環境...")
    if VENV_DIR.exists():
        print(f"[Setup] 發現舊的測試環境，正在清理...")
        shutil.rmtree(VENV_DIR)

    try:
        # 使用 uv 建立 venv
        subprocess.run(
            ["uv", "venv", VENV_DIR, "--seed"],
            check=True, capture_output=True, text=True, timeout=120
        )
        print(f"[Setup] 虛擬環境建立成功。")

        # 2. 安裝依賴
        print(f"[Setup] 正在安裝服務依賴 from {REQ_FILE}...")
        subprocess.run(
            [str(PYTHON_EXEC), "-m", "pip", "install", "-r", str(REQ_FILE)],
            check=True, capture_output=True, text=True, timeout=180
        )
        print(f"[Setup] 依賴安裝成功。")

        # 3. 啟動服務
        print(f"[Setup] 正在啟動 key_service 於埠號 {service_port}...")
        env = os.environ.copy()
        env["PORT"] = str(service_port)

        # 使用 Popen 以非阻塞方式啟動服務，並將日誌重定向到檔案
        stdout_log_path = SERVICE_DIR / "test_stdout.log"
        stderr_log_path = SERVICE_DIR / "test_stderr.log"
        with open(stdout_log_path, "w") as stdout_log, open(stderr_log_path, "w") as stderr_log:
            process = subprocess.Popen(
                [str(PYTHON_EXEC), str(MAIN_SCRIPT)],
                env=env,
                stdout=stdout_log,
                stderr=stderr_log
            )

        # 4. 健康檢查：等待服務就緒
        start_time = time.time()
        service_ready = False
        last_error = ""
        while time.time() - start_time < 60: # 最多等待 60 秒
            try:
                response = requests.get(health_check_url, timeout=1)
                if response.status_code == 200:
                    print(f"[Setup] 服務健康檢查成功！")
                    service_ready = True
                    break
            except requests.exceptions.RequestException as e:
                last_error = str(e)
                time.sleep(1)

        if not service_ready:
            # 如果服務啟動失敗，清理並引發錯誤
            process.terminate()
            # 讀取日誌檔案內容以供除錯
            stdout_content = stdout_log_path.read_text() if stdout_log_path.exists() else "STDOUT log not found."
            stderr_content = stderr_log_path.read_text() if stderr_log_path.exists() else "STDERR log not found."

            print(f"[Setup] 服務啟動失敗！最後的連線錯誤: {last_error}")
            print(f"[Setup] STDOUT:\n{stdout_content}")
            print(f"[Setup] STDERR:\n{stderr_content}")

            if VENV_DIR.exists():
                shutil.rmtree(VENV_DIR)
            pytest.fail(f"服務未能在 60 秒內啟動。查看日誌以了解詳情。")

        # --- Yield ---
        # 將 API 的基礎 URL 交給測試函式
        yield base_api_url

        # --- Teardown ---
        print(f"\n[Teardown] 正在關閉服務並清理環境...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()

        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        print(f"[Teardown] 環境清理完畢。")

    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # 如果在 Setup 過程中出錯，也要確保清理
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        pytest.fail(f"測試環境設定失敗: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}")
    except Exception as e:
        if VENV_DIR.exists():
            shutil.rmtree(VENV_DIR)
        pytest.fail(f"測試環境設定時發生未預期錯誤: {e}")

# --- 測試函式 ---

def test_get_initial_keys_is_empty(key_service_environment):
    """測試：服務剛啟動時，金鑰列表應為空。"""
    base_url = key_service_environment
    response = requests.get(f"{base_url}/api/keys", timeout=10)
    assert response.status_code == 200
    assert response.json() == []

def test_add_and_delete_key(key_service_environment):
    """測試：新增一個金鑰，然後再將其刪除。"""
    base_url = key_service_environment
    # 請注意：此處的金鑰是範例，不具有實際效力
    api_key_to_test = f"AIzaSyZ_DUMMY_KEY_FOR_TESTING_{int(time.time())}"
    key_name = "MyTestKey"

    # 1. 新增金鑰
    add_response = requests.post(
        f"{base_url}/api/keys",
        json={"api_key": api_key_to_test, "name": key_name},
        timeout=45 # 驗證金鑰可能需要時間
    )
    assert add_response.status_code == 200
    add_data = add_response.json()
    assert add_data["name"] == key_name
    assert "key_hash" in add_data
    key_hash = add_data["key_hash"]

    # 2. 驗證金鑰已存在
    get_response = requests.get(f"{base_url}/api/keys", timeout=10)
    assert get_response.status_code == 200
    keys_list = get_response.json()
    assert len(keys_list) == 1
    assert keys_list[0]["key_hash"] == key_hash
    assert keys_list[0]["key_name"] == key_name

    # 3. 刪除金鑰
    delete_response = requests.delete(f"{base_url}/api/keys/{key_hash}", timeout=10)
    assert delete_response.status_code == 200
    assert delete_response.json()["message"] == "金鑰已成功刪除。"

    # 4. 驗證金鑰已被刪除
    final_get_response = requests.get(f"{base_url}/api/keys", timeout=10)
    assert final_get_response.status_code == 200
    assert final_get_response.json() == []

def test_add_duplicate_key_fails(key_service_environment):
    """測試：新增重複的金鑰應該會失敗。"""
    base_url = key_service_environment
    api_key_to_test = f"AIzaSyA_ANOTHER_DUMMY_KEY_{int(time.time())}"

    # 第一次新增
    add_response1 = requests.post(
        f"{base_url}/api/keys",
        json={"api_key": api_key_to_test, "name": "UniqueKey"},
        timeout=45
    )
    assert add_response1.status_code == 200
    key_hash = add_response1.json()["key_hash"]

    # 第二次新增（應該失敗）
    add_response2 = requests.post(
        f"{base_url}/api/keys",
        json={"api_key": api_key_to_test, "name": "DuplicateKey"},
        timeout=45
    )
    assert add_response2.status_code == 409 # 409 Conflict
    assert "此 API 金鑰已存在" in add_response2.json()["detail"]

    # 清理
    requests.delete(f"{base_url}/api/keys/{key_hash}", timeout=10)
