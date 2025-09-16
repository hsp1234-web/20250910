import pytest
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

# --- 測試環境路徑設定 ---
# 這些是標準庫和 pytest，可以安全地在頂層匯入
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# --- 常數 ---
FROZEN_THRESHOLD = 10

# --- Mock Gemini API Exception ---
class MockGoogleAPIError(Exception):
    """模擬 Google API 的特定錯誤。"""
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return self.message

@pytest.fixture
def file_db_for_poc(tmp_path, monkeypatch):
    """
    一個為 V3 POC 建立的、基於暫存檔案的資料庫 fixture。
    它確保所有模組在測試期間共享同一個資料庫實例。
    """
    # 將模組匯入移至 fixture 內部
    from db import initialize_database
    from core import key_manager

    # 1. 在暫存目錄中建立一個唯一的資料庫檔案路徑
    temp_db_path = tmp_path / "poc_test.db"

    # 2. Patch 所有相關模組的 DB_PATH
    monkeypatch.setattr(initialize_database, 'DB_PATH', temp_db_path)
    monkeypatch.setattr(key_manager, 'DB_PATH', temp_db_path)

    # 延遲匯入 key_health_manager 並 patch
    from core import key_health_manager
    monkeypatch.setattr(key_health_manager, 'DB_PATH', temp_db_path)

    # 3. 執行標準的資料庫初始化流程
    initialize_database.initialize()

    # 4. 預先填入測試用的金鑰
    conn = sqlite3.connect(temp_db_path)
    cursor = conn.cursor()
    mock_keys = []
    for i in range(5):
        key_value = f"test-key-value-{i}"
        key_hash = key_manager._hash_key(key_value)
        mock_keys.append({
            "name": f"TEST_KEY_{i}",
            "value": key_value,
            "hash": key_hash
        })
        cursor.execute(
            "INSERT INTO api_keys (key_name, key_hash, key_value, is_valid, status) VALUES (?, ?, ?, ?, ?)",
            (f"TEST_KEY_{i}", key_hash, key_value, True, 'active')
        )
    conn.commit()

    # 5. Yield 一個查詢函式和 mock 金鑰列表
    def db_checker(query, params=()):
        c = sqlite3.connect(temp_db_path)
        c.row_factory = sqlite3.Row
        cursor = c.cursor()
        cursor.execute(query, params)
        result = cursor.fetchone()
        c.close()
        return result

    yield db_checker, mock_keys
    conn.close()

def test_poc_cooldown_and_freeze_flow(file_db_for_poc, monkeypatch):
    """
    端到端測試 V3 POC 的冷卻與冷凍流程 (使用延遲匯入)。
    """
    # --- 步驟 0: 在匯入前，先注入 Mock ---
    # 這是解決模組載入時依賴問題的關鍵
    # 我們需要模擬一個完整的套件結構
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_google.generativeai = mock_genai

    monkeypatch.setitem(sys.modules, 'google', mock_google)
    monkeypatch.setitem(sys.modules, 'google.generativeai', mock_genai)
    monkeypatch.setitem(sys.modules, 'google.generativeai.types', mock_genai.types)
    monkeypatch.setitem(sys.modules, 'PIL', MagicMock())

    # --- 步驟 1: 現在可以安全地匯入我們的模組了 ---
    from core import key_manager
    from tools import gemini_manager

    db_checker, mock_keys = file_db_for_poc

    TARGET_KEY_HASH = mock_keys[2]['hash']
    TARGET_KEY_VALUE = mock_keys[2]['value']

    # --- 步驟 2: 設定 Mock 的行為 ---
    mock_genai.types.GenerationConfig.return_value = "mock_config"
    mock_model_instance = MagicMock()

    def mock_generate_content(*args, **kwargs):
        current_key = mock_genai.api_key
        if current_key == TARGET_KEY_VALUE:
            raise MockGoogleAPIError("429 Resource has been exhausted")
        else:
            mock_response = MagicMock()
            type(mock_response).text = PropertyMock(return_value='"Success"')
            type(mock_response).usage_metadata = PropertyMock(return_value={'total_token_count': 10})
            return mock_response

    mock_model_instance.generate_content.side_effect = mock_generate_content
    mock_genai.GenerativeModel.return_value = mock_model_instance

    def custom_configure(api_key, **kwargs):
        mock_genai.api_key = api_key
    mock_genai.configure.side_effect = custom_configure

    # --- 步驟 3: 執行測試 ---
    all_keys = key_manager.get_all_valid_keys_for_manager()
    assert len(all_keys) == 5

    gemini = gemini_manager.GeminiManager(all_keys, cooldown_seconds=1)

    # 為了測試確定性，強制 gemini manager 只使用我們的目標金鑰
    target_api_key_obj = next((k for k in gemini.key_pool if k.hash == TARGET_KEY_HASH), None)
    assert target_api_key_obj is not None, "在金鑰池中找不到目標測試金鑰"

    # 連續觸發錯誤，直到冷凍
    for i in range(FROZEN_THRESHOLD):
        # 在每次迭代中，重設 manager 的狀態，以確保我們的目標金鑰被使用
        gemini.key_pool = [target_api_key_obj]
        gemini.cooldown_keys.clear()

        # 呼叫 API，這將觸發我們 mock 的 429 錯誤
        gemini._api_call_wrapper("test", "model", ["prompt"])

        # 驗證中間狀態
        if i < FROZEN_THRESHOLD - 1:
            status_row = db_checker("SELECT status, cooldown_count FROM api_keys WHERE key_hash = ?", (TARGET_KEY_HASH,))
            assert status_row[0] == 'cooldown'
            assert status_row[1] == i + 1

    # --- 步驟 4: 驗證資料庫狀態 ---
    # 驗證金鑰已被冷凍
    key_state = db_checker("SELECT status, cooldown_count, frozen_until FROM api_keys WHERE key_hash = ?", (TARGET_KEY_HASH,))
    assert key_state is not None, "找不到目標金鑰"
    # 經過 10 次失敗，應該剛好達到冷凍閾值並被冷凍
    assert key_state[0] == 'frozen', f"預期狀態為 'frozen'，但實際為 '{key_state[0]}'"
    assert key_state[1] == 0, "冷凍後 cooldown_count 應歸零"
    assert key_state[2] is not None, "frozen_until 不應為空"

    # 驗證 key_manager 現在會過濾掉這把金鑰
    keys_after_freeze = key_manager.get_all_valid_keys_for_manager()
    assert len(keys_after_freeze) == 4

    found_frozen_key = any(k['hash'] == TARGET_KEY_HASH for k in keys_after_freeze)
    assert not found_frozen_key, "被冷凍的金鑰不應該再被 key_manager 選取"

    print("\n測試成功：金鑰在連續失敗後，狀態成功變為 'frozen'，並被 key_manager 過濾。")
