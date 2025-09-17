import sys
from pathlib import Path
import pytest

# --- 路徑修正，確保可以從 tests 目錄找到 src ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

# --- 導入待測試的目標 ---
from tools.gemini_manager import GeminiManager, ApiKey

# --- 簡單的導入測試 ---

def test_import_orchestrator():
    """測試：確保核心協調器模組可以被成功導入。"""
    try:
        from core import orchestrator
    except ImportError as e:
        pytest.fail(f"無法導入 'orchestrator' 模組: {e}")

def test_import_gemini_processor():
    """測試：確保 Gemini 處理器模組可以被成功導入。"""
    try:
        from tools import gemini_processor
    except ImportError as e:
        pytest.fail(f"無法導入 'gemini_processor' 模組: {e}")

# --- GeminiManager 的單元測試 ---

class TestGeminiManager:
    """針對簡化後的 GeminiManager 的測試套件。"""

    def test_initialization_with_keys(self):
        """測試：使用有效的金鑰列表初始化 GeminiManager。"""
        api_keys_data = [
            {'name': 'key_1', 'value': 'value_1'},
            {'name': 'key_2', 'value': 'value_2'}
        ]

        manager = GeminiManager(api_keys=api_keys_data)

        assert len(manager.api_keys) == 2
        assert isinstance(manager.api_keys[0], ApiKey)
        assert manager.api_keys[0].name == 'key_1'
        assert manager.api_keys[1].key == 'value_2'

    def test_initialization_with_empty_list(self):
        """
        測試：使用空的金鑰列表初始化 GeminiManager。
        這是針對先前 ValueError 錯誤的迴歸測試。
        """
        # 這個操作不應該引發任何錯誤
        try:
            manager = GeminiManager(api_keys=[])
            assert manager.api_keys == []
        except ValueError:
            pytest.fail("GeminiManager 不應在使用空列表初始化時引發 ValueError。")

    def test_get_all_keys(self):
        """測試：get_all_keys() 方法是否能正確返回所有金鑰。"""
        api_keys_data = [
            {'name': 'key_1', 'value': 'value_1'}
        ]

        manager = GeminiManager(api_keys=api_keys_data)

        all_keys = manager.get_all_keys()

        assert len(all_keys) == 1
        assert isinstance(all_keys[0], ApiKey)
        assert all_keys[0].name == 'key_1'
        assert all_keys[0].key == 'value_1'

    def test_get_all_keys_when_empty(self):
        """測試：當初始化為空時，get_all_keys() 應返回空列表。"""
        manager = GeminiManager(api_keys=[])
        all_keys = manager.get_all_keys()
        assert all_keys == []
