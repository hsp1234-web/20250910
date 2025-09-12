import sys
import unittest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
from collections import deque

# --- 路徑修正，確保可以從 tests 目錄找到 src ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.gemini_manager import GeminiManager, ApiKey

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
    def test_successful_call_on_first_key(self, mock_genai):
        """測試：第一個金鑰就成功的情況"""
        # 設定
        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = '{"message": "success"}'
        mock_genai.GenerativeModel.return_value = mock_model

        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success"})
        self.assertIsNone(error)
        self.assertEqual(used_key_name, "key_1")
        mock_genai.configure.assert_called_once_with(api_key='value_1')
        mock_model.generate_content.assert_called_once()

        # 斷言金鑰池已輪換，成功的 key_1 現在在末尾
        self.assertEqual(manager.key_pool[0].name, 'key_2')
        self.assertEqual(manager.key_pool[-1].name, 'key_1')

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    def test_failover_on_quota_error(self, mock_genai):
        """測試：第一個金鑰配額用盡，應自動轉移到第二個金鑰並成功"""
        # 設定
        # 模擬第一個金鑰拋出配額錯誤，第二個金鑰正常回傳
        mock_model_fail = MagicMock()
        mock_model_fail.generate_content.side_effect = Exception("Resource has been exhausted (e.g. check quota).")

        mock_model_success = MagicMock()
        mock_model_success.generate_content.return_value.text = '{"message": "success_on_key_2"}'

        # 讓 GenerativeModel 根據 api_key 回傳不同的 mock model
        def model_side_effect(model_name):
            api_key = mock_genai.configure.call_args.kwargs['api_key']
            if api_key == 'value_1':
                return mock_model_fail
            return mock_model_success

        mock_genai.GenerativeModel.side_effect = model_side_effect

        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success_on_key_2"})
        self.assertIsNone(error)
        self.assertEqual(used_key_name, "key_2")

        # 驗證 configure 被呼叫了兩次，分別用 key_1 和 key_2
        self.assertEqual(mock_genai.configure.call_count, 2)
        mock_genai.configure.assert_has_calls([
            call(api_key='value_1'),
            call(api_key='value_2')
        ])

        # 驗證 generate_content 也被呼叫了兩次
        self.assertEqual(mock_model_fail.generate_content.call_count, 1)
        self.assertEqual(mock_model_success.generate_content.call_count, 1)

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    @patch('tools.gemini_manager.time.sleep', return_value=None) # 避免在測試中實際等待
    def test_retry_on_transient_error_then_succeed(self, mock_sleep, mock_genai):
        """測試：遇到暫時性錯誤時，應在同一個金鑰上重試並成功"""
        # 設定
        mock_model = MagicMock()
        # 第一次呼叫拋出 500 錯誤，第二次正常回傳
        mock_model.generate_content.side_effect = [
            Exception("500 Internal Server Error"),
            MagicMock(text='{"message": "success_after_retry"}')
        ]
        mock_genai.GenerativeModel.return_value = mock_model

        manager = GeminiManager(api_keys=self.api_keys_data, max_retries=3)

        # 執行
        result, error, used_key_name = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertEqual(result, {"message": "success_after_retry"})
        self.assertIsNone(error)
        self.assertEqual(used_key_name, "key_1")

        # 驗證 configure 只用第一個金鑰呼叫了一次
        mock_genai.configure.assert_called_once_with(api_key='value_1')

        # 驗證 generate_content 被呼叫了兩次
        self.assertEqual(mock_model.generate_content.call_count, 2)
        # 驗證 sleep 被呼叫了一次
        mock_sleep.assert_called_once()

    @patch('tools.gemini_manager.GenerationConfig', MagicMock())
    @patch('tools.gemini_manager.genai')
    def test_all_keys_fail(self, mock_genai):
        """測試：所有金鑰都失敗的情況"""
        # 設定
        # 讓所有金鑰都拋出永久性錯誤
        mock_model = MagicMock()
        mock_model.generate_content.side_effect = Exception("Resource has been exhausted (e.g. check quota).")
        mock_genai.GenerativeModel.return_value = mock_model

        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        result, error, used_key_name = manager._api_call_wrapper(
            "test_task", "test_model", ["prompt"], "json"
        )

        # 斷言
        self.assertIsNone(result)
        self.assertIsNotNone(error)
        self.assertIn("quota", str(error))
        self.assertEqual(used_key_name, "all_keys_failed")

        # 驗證 configure 被呼叫了三次，每個金鑰都試了一次
        self.assertEqual(mock_genai.configure.call_count, 3)
        mock_genai.configure.assert_has_calls([
            call(api_key='value_1'),
            call(api_key='value_2'),
            call(api_key='value_3')
        ])

    @patch('tools.gemini_manager.genai')
    def test_list_available_models(self, mock_genai):
        """測試 list_available_models 是否能正確篩選並回傳模型。"""
        # 設定
        # 模擬 google.generativeai.list_models() 的回傳值
        mock_model_1 = MagicMock()
        mock_model_1.name = "models/gemini-pro"
        mock_model_1.supported_generation_methods = ["generateContent", "otherMethod"]

        mock_model_2 = MagicMock()
        mock_model_2.name = "models/gemini-pro-vision"
        mock_model_2.supported_generation_methods = ["generateContent"]

        mock_model_3 = MagicMock()
        mock_model_3.name = "models/text-embedding-004"
        mock_model_3.supported_generation_methods = ["embedContent"] # 不支援 generateContent

        mock_model_4 = MagicMock()
        mock_model_4.name = "models/aqa"
        mock_model_4.supported_generation_methods = ["generateAnswer"] # 不支援 generateContent

        mock_genai.list_models.return_value = [
            mock_model_1, mock_model_2, mock_model_3, mock_model_4
        ]

        manager = GeminiManager(api_keys=self.api_keys_data)

        # 執行
        available_models = manager.list_available_models()

        # 斷言
        # 1. genai.configure 應該被第一個金鑰呼叫
        mock_genai.configure.assert_called_once_with(api_key='value_1')

        # 2. list_models 應該被呼叫
        mock_genai.list_models.assert_called_once()

        # 3. 回傳的列表應該只包含支援 'generateContent' 的模型名稱
        self.assertEqual(len(available_models), 2)
        self.assertIn("models/gemini-pro", available_models)
        self.assertIn("models/gemini-pro-vision", available_models)
        self.assertNotIn("models/text-embedding-004", available_models)


if __name__ == '__main__':
    unittest.main()
