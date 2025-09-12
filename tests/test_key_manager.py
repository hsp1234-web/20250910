# tests/test_key_manager.py
import pytest
import sys
import os
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

# --- 路徑修正，確保可以從 src 匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# 在匯入前設定環境變數，避免真實的金鑰檔案被讀取
# 我們將在 fixture 中明確設定 KEYS_FILE 路徑
from core import key_manager

@pytest.fixture
def mock_keys_file(tmp_path):
    """
    一個 pytest fixture，它會：
    1. 建立一個暫時的 secrets 目錄。
    2. 在 key_manager 中 mock KEYS_FILE 常數，使其指向一個暫時的檔案。
    3. 確保測試結束後檔案會被清理。
    """
    temp_secrets_dir = tmp_path / "secrets"
    temp_secrets_dir.mkdir()
    temp_keys_file = temp_secrets_dir / "keys.json"

    # 使用 patch 來動態修改 key_manager 中的 KEYS_FILE 常數
    with patch.object(key_manager, 'KEYS_FILE', temp_keys_file):
        yield temp_keys_file

# --- 測試開始 ---

@patch('core.key_manager._validate_single_key', return_value=True)
def test_add_key_success(mock_validate, mock_keys_file):
    """測試成功新增一個金鑰。"""
    result = key_manager.add_key("test-api-key-1", "My First Key")

    assert result['name'] == "My First Key"
    assert result['is_valid'] is True
    assert 'key_hash' in result

    # 驗證檔案內容
    with open(mock_keys_file, 'r') as f:
        keys_in_file = json.load(f)

    assert len(keys_in_file) == 1
    saved_key = keys_in_file[0]
    assert saved_key['key_value'] == "test-api-key-1"
    assert saved_key['name'] == "My First Key"
    assert saved_key['is_valid'] is True
    assert 'last_validated' in saved_key

@patch('core.key_manager._validate_single_key', return_value=True)
def test_add_duplicate_key_raises_error(mock_validate, mock_keys_file):
    """測試新增重複的金鑰時會引發 ValueError。"""
    key_manager.add_key("test-api-key-1", "Key 1")

    with pytest.raises(ValueError, match="此 API 金鑰已存在。"):
        key_manager.add_key("test-api-key-1", "Key 1 Duplicate")

    # 確認檔案中仍然只有一個金鑰
    with open(mock_keys_file, 'r') as f:
        keys_in_file = json.load(f)
    assert len(keys_in_file) == 1

def test_get_all_keys_security(mock_keys_file):
    """測試 get_all_keys 不會回傳原始金鑰值。"""
    # 手動建立一個包含金鑰的檔案
    key_data = [{
        "name": "Secure Key",
        "key_value": "secret-raw-key-value",
        "key_hash": "somehash",
        "is_valid": True,
        "last_validated": "sometime"
    }]
    with open(mock_keys_file, 'w') as f:
        json.dump(key_data, f)

    retrieved_keys = key_manager.get_all_keys()
    assert len(retrieved_keys) == 1

    key_info = retrieved_keys[0]
    assert "key_value" not in key_info
    assert key_info['name'] == "Secure Key"
    assert key_info['key_hash'] == "somehash"

@patch('core.key_manager._validate_single_key', return_value=True)
def test_delete_key(mock_validate, mock_keys_file):
    """測試刪除一個已存在的金鑰。"""
    # 先新增兩個金鑰
    key_manager.add_key("key-to-delete", "ToDelete")
    key_manager.add_key("key-to-keep", "ToKeep")

    keys = key_manager.get_all_keys()
    assert len(keys) == 2

    hash_to_delete = key_manager._hash_key("key-to-delete")

    # 執行刪除
    delete_result = key_manager.delete_key(hash_to_delete)
    assert delete_result is True

    # 驗證結果
    keys_after_delete = key_manager.get_all_keys()
    assert len(keys_after_delete) == 1
    assert keys_after_delete[0]['name'] == "ToKeep"

def test_delete_non_existent_key(mock_keys_file):
    """測試刪除一個不存在的金鑰時，函式會回傳 False 且不引發錯誤。"""
    delete_result = key_manager.delete_key("non-existent-hash")
    assert delete_result is False
