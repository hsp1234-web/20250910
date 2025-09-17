# tests/test_key_manager.py
import pytest
import sys
from unittest.mock import patch
from pathlib import Path

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from core import key_manager
from db.database import initialize_database

@pytest.fixture
def test_db(tmp_path):
    """一個提供乾淨資料庫路徑並確保初始化的 fixture"""
    db_path = tmp_path / "test_key_manager.db"
    # 使用這個暫存資料庫路徑來初始化
    conn = key_manager.sqlite3.connect(db_path)
    initialize_database(conn)
    conn.close()
    return db_path

# --- 測試開始 ---

@patch('core.key_manager._validate_single_key', return_value=True)
def test_add_key_success(mock_validate, test_db, monkeypatch):
    """測試成功新增一個金鑰到資料庫。"""
    monkeypatch.setattr(key_manager, 'DB_PATH', test_db)

    result = key_manager.add_key("test-api-key-1", "My First Key")

    assert result['name'] == "My First Key"
    assert result['is_valid'] is True
    assert 'key_hash' in result

    conn = key_manager.sqlite3.connect(test_db)
    conn.row_factory = key_manager.sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE key_hash = ?", (result['key_hash'],))
    row = cursor.fetchone()
    conn.close()

    assert row is not None
    assert row['key_value'] == "test-api-key-1"
    assert row['key_name'] == "My First Key"
    assert row['is_valid'] == 1

@patch('core.key_manager._validate_single_key', return_value=True)
def test_add_duplicate_key_raises_error(mock_validate, test_db, monkeypatch):
    """測試新增重複的金鑰時會引發 ValueError。"""
    monkeypatch.setattr(key_manager, 'DB_PATH', test_db)
    key_manager.add_key("test-api-key-1", "Key 1")

    with pytest.raises(ValueError, match="此 API 金鑰已存在。"):
        key_manager.add_key("test-api-key-1", "Key 1 Duplicate")

    conn = key_manager.sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM api_keys")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 1

def test_get_all_keys_security(test_db, monkeypatch):
    """測試 get_all_keys 不會回傳原始金鑰值。"""
    monkeypatch.setattr(key_manager, 'DB_PATH', test_db)
    conn = key_manager.sqlite3.connect(test_db)
    key_hash = key_manager._hash_key("secret-raw-key-value")
    conn.execute(
        "INSERT INTO api_keys (key_name, key_hash, key_value, is_valid) VALUES (?, ?, ?, ?)",
        ("Secure Key", key_hash, "secret-raw-key-value", 1)
    )
    conn.commit()
    conn.close()

    retrieved_keys = key_manager.get_all_keys()
    assert len(retrieved_keys) == 1

    key_info = retrieved_keys[0]
    assert "key_value" not in key_info
    assert key_info['name'] == "Secure Key"
    assert key_info['key_hash'] == key_hash

@patch('core.key_manager._validate_single_key', return_value=True)
def test_delete_key(mock_validate, test_db, monkeypatch):
    """測試從資料庫刪除一個已存在的金鑰。"""
    monkeypatch.setattr(key_manager, 'DB_PATH', test_db)
    key_manager.add_key("key-to-delete", "ToDelete")
    key_manager.add_key("key-to-keep", "ToKeep")

    keys = key_manager.get_all_keys()
    assert len(keys) == 2

    hash_to_delete = key_manager._hash_key("key-to-delete")
    delete_result = key_manager.delete_key(hash_to_delete)
    assert delete_result is True

    keys_after_delete = key_manager.get_all_keys()
    assert len(keys_after_delete) == 1
    assert keys_after_delete[0]['name'] == "ToKeep"

def test_delete_non_existent_key(test_db, monkeypatch):
    """測試刪除一個不存在的金鑰時，函式會回傳 False 且不引發錯誤。"""
    monkeypatch.setattr(key_manager, 'DB_PATH', test_db)
    delete_result = key_manager.delete_key("non-existent-hash")
    assert delete_result is False
