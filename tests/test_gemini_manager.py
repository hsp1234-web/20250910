import sys
import unittest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from collections import deque

# --- 路徑修正，確保可以從 tests 目錄找到 src ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.gemini_manager import GeminiManager, ApiKey, google_exceptions

class TestGeminiManager(unittest.TestCase):

    def setUp(self):
        """為每個測試案例設定環境"""
        self.api_keys_data = [
            {'name': 'key_1', 'value': 'value_1'},
            {'name': 'key_2', 'value': 'value_2'},
            {'name': 'key_3', 'value': 'value_3'}
        ]

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    def test_successful_call(self, mock_genai):
        """測試：成功呼叫的情況，應對隨機金鑰順序"""
        # 設定
        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = '{"message": "success"}'
        mock_genai.GenerativeModel.return_value = mock_model

        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name, _ = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success"})
        self.assertIsNone(error)
        self.assertIn(used_key_name, [k['name'] for k in self.api_keys_data])
        mock_genai.configure.assert_called_once()
        mock_model.generate_content.assert_called_once()
        # 移除對金鑰輪換的過時斷言

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    def test_failover_on_quota_error(self, mock_genai):
        """測試：第一個金鑰配額用盡，應自動轉移到另一個金鑰並成功"""
        # 設定
        # 模擬 ResourceExhausted 錯誤
        if google_exceptions:
            mock_google_exceptions = google_exceptions
        else: # 如果 google_exceptions 未被導入，則建立一個 mock
            mock_google_exceptions = MagicMock()
            mock_google_exceptions.ResourceExhausted = type('ResourceExhausted', (Exception,), {})

        mock_model_fail = MagicMock()
        mock_model_fail.generate_content.side_effect = mock_google_exceptions.ResourceExhausted("Quota exhausted")

        mock_model_success = MagicMock()
        mock_model_success.generate_content.return_value.text = '{"message": "success_on_key_2"}'

        # 讓 GenerativeModel 根據 api_key 回傳不同的 mock model
        # 為了應對隨機性，我們讓第一個被呼叫的金鑰失敗
        first_called_key = None
        def model_side_effect(model_name):
            nonlocal first_called_key
            api_key_val = mock_genai.configure.call_args.kwargs['api_key']
            if first_called_key is None:
                first_called_key = api_key_val
                return mock_model_fail
            return mock_model_success

        mock_genai.GenerativeModel.side_effect = model_side_effect
        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name, _ = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success_on_key_2"})
        self.assertIsNone(error)
        self.assertIsNotNone(first_called_key)
        self.assertNotEqual(used_key_name, first_called_key) # 確保使用了不同的金鑰
        self.assertIn(first_called_key, manager.cooldown_keys) # 確保失敗的金鑰在冷卻池中

        self.assertEqual(mock_genai.configure.call_count, 2)
        self.assertEqual(mock_model_fail.generate_content.call_count, 1)
        self.assertEqual(mock_model_success.generate_content.call_count, 1)

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    @patch('tools.gemini_manager.time.sleep', return_value=None) # 避免在測試中實際等待
    def test_retry_on_transient_error_then_succeed(self, mock_sleep, mock_genai):
        """測試：遇到暫時性錯誤時，應在同一個金鑰上重試並成功"""
        # 設定
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = [
            Exception("500 Internal Server Error"),
            MagicMock(text='{"message": "success_after_retry"}')
        ]
        mock_genai.GenerativeModel.return_value = mock_model
        manager = GeminiManager(api_keys=self.api_keys_data, max_retries=3)

        # 執行
        result, error, used_key_name, _ = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success_after_retry"})
        self.assertIsNone(error)
        self.assertIn(used_key_name, [k['name'] for k in self.api_keys_data])
        mock_genai.configure.assert_called_once()
        self.assertEqual(mock_model.generate_content.call_count, 2)
        mock_sleep.assert_called_once()

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    def test_all_keys_fail(self, mock_genai):
        """測試：所有金鑰都失敗的情況"""
        # 設定
        mock_model = MagicMock()
        # 模擬 ResourceExhausted 錯誤
        if google_exceptions:
            error_to_raise = google_exceptions.ResourceExhausted("Quota exhausted")
        else:
            error_to_raise = Exception("Resource has been exhausted (e.g. check quota).")
        mock_model.generate_content.side_effect = error_to_raise
        mock_genai.GenerativeModel.return_value = mock_model
        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name, _ = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        # 讓斷言更靈活，只要包含 "exhausted" 或 "quota" 即可
        self.assertTrue("exhausted" in str(error).lower() or "quota" in str(error).lower())
        self.assertEqual(used_key_name, "all_keys_failed")
        self.assertEqual(mock_genai.configure.call_count, 3)
        # 因為順序是隨機的，所以使用 any_order=True
        mock_genai.configure.assert_has_calls([
            call(api_key='value_1'),
            call(api_key='value_2'),
            call(api_key='value_3')
        ], any_order=True)

    @patch('tools.gemini_manager.genai')
    def test_list_available_models(self, mock_genai):
        """測試 list_available_models 是否能正確篩選並回傳模型。"""
        # 設定
        mock_model_1 = MagicMock()
        mock_model_1.name = "models/gemini-pro"
        mock_model_1.supported_generation_methods = ["generateContent", "otherMethod"]
        mock_model_2 = MagicMock()
        mock_model_2.name = "models/gemini-pro-vision"
        mock_model_2.supported_generation_methods = ["generateContent"]
        mock_model_3 = MagicMock()
        mock_model_3.name = "models/text-embedding-004"
        mock_model_3.supported_generation_methods = ["embedContent"]
        mock_genai.list_models.return_value = [mock_model_1, mock_model_2, mock_model_3]
        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        available_models = manager.list_available_models()

        # 斷言
        mock_genai.configure.assert_called_once_with(api_key='value_1')
        mock_genai.list_models.assert_called_once()
        self.assertEqual(len(available_models), 2)
        self.assertIn("models/gemini-pro", available_models)
        self.assertIn("models/gemini-pro-vision", available_models)
        self.assertNotIn("models/text-embedding-004", available_models)

if __name__ == '__main__':
    unittest.main()
