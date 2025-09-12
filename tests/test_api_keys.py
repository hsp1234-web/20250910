import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# --- 測試環境路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# 匯入 FastAPI 主應用程式
# 注意：我們需要在設定好測試環境（例如 monkeypatch）後才匯入
from api.api_server import app

# --- 整合測試案例 ---

def test_keys_api_lifecycle(db_conn, monkeypatch):
    """
    這是一個完整的整合測試，用於驗證金鑰管理 API 的整個生命週期。
    它會測試：
    1. 獲取空的金鑰列表。
    2. 新增一個金鑰。
    3. 獲取包含一個金鑰的列表。
    4. 刪除該金鑰。
    5. 再次獲取空的金鑰列表。
    """
    # --- 隔離檔案系統 ---
    # 建立一個假的、記憶體內的資料庫來取代 keys.json，以確保測試的隔離性
    mock_keys_db = []

    def mock_load_keys():
        return mock_keys_db.copy()

    def mock_save_keys(keys):
        nonlocal mock_keys_db
        mock_keys_db = keys

    monkeypatch.setattr("core.key_manager._load_keys", mock_load_keys)
    monkeypatch.setattr("core.key_manager._save_keys", mock_save_keys)

    # 模擬 key_manager 的金鑰驗證，因為我們不想在測試中真的去呼叫 Google API
    # 我們讓它總是回傳 True，代表任何金鑰都是有效的
    monkeypatch.setattr("core.key_manager._validate_single_key", lambda key: True)

    # 建立一個 FastAPI 測試客戶端
    client = TestClient(app)

    # --- 1. 初始狀態：獲取空的金鑰列表 ---
    print("\n--- 步驟 1: 獲取初始空列表 ---")
    response_get_initial = client.get("/api/keys")
    assert response_get_initial.status_code == 200
    assert response_get_initial.json() == []
    print("✅ 成功獲取空的金鑰列表。")

    # --- 2. 新增一個金鑰 ---
    print("\n--- 步驟 2: 新增一個 API 金鑰 ---")
    key_payload = {"api_key": "test-key-12345", "name": "我的測試金鑰"}
    response_add = client.post("/api/keys", json=key_payload)
    assert response_add.status_code == 200
    add_json = response_add.json()
    assert add_json["message"] == "金鑰 '我的測試金鑰' 已新增。"
    assert "key_hash" in add_json
    key_hash = add_json["key_hash"] # 儲存金鑰的雜湊值以供後續使用
    print(f"✅ 成功新增金鑰，雜湊值: {key_hash}")

    # --- 3. 驗證金鑰已存在 ---
    print("\n--- 步驟 3: 驗證金鑰已存在於列表中 ---")
    response_get_one = client.get("/api/keys")
    assert response_get_one.status_code == 200
    get_one_json = response_get_one.json()
    assert len(get_one_json) == 1
    key_in_list = get_one_json[0]
    assert key_in_list["key_hash"] == key_hash
    assert key_in_list["name"] == "我的測試金鑰"
    assert key_in_list["is_valid"] is True # 因為我們 mock 了 test_key
    print("✅ 成功在列表中找到新增的金鑰。")

    # --- 4. 刪除該金鑰 ---
    print(f"\n--- 步驟 4: 刪除雜湊值為 {key_hash} 的金鑰 ---")
    response_delete = client.delete(f"/api/keys/{key_hash}")
    assert response_delete.status_code == 200
    assert response_delete.json()["message"] == "金鑰已成功刪除。"
    print("✅ 成功刪除金鑰。")

    # --- 5. 最終狀態：再次獲取空的金鑰列表 ---
    print("\n--- 步驟 5: 驗證列表再次為空 ---")
    response_get_final = client.get("/api/keys")
    assert response_get_final.status_code == 200
    assert response_get_final.json() == []
    print("✅ 成功確認金鑰列表已清空。")
    print("\n🎉 金鑰管理 API 生命週期整合測試成功！")
