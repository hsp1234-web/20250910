# tests/managers/test_readiness_manager.py
import pytest
import threading
from unittest.mock import patch, MagicMock

# 為了讓測試能找到 `core` 模組
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

from core.managers.readiness_manager import ReadinessManager

@pytest.fixture
def mock_requests_post():
    """模擬 requests.post 函式。"""
    with patch('requests.post') as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        yield mock_post

@pytest.fixture
def mock_signal_file():
    """模擬 Path 物件，以監控檔案操作。"""
    with patch('pathlib.Path') as mock_path_class:
        mock_instance = MagicMock()
        mock_path_class.return_value = mock_instance
        yield mock_instance

def test_run_in_background_success(mock_requests_post, mock_signal_file):
    """
    測試：在 API 成功就緒時，ReadinessManager 的正常執行流程。
    """
    api_port = 8000
    api_ready_event = threading.Event()

    manager = ReadinessManager(api_port, api_ready_event)
    manager.readiness_signal_file = mock_signal_file # 替換為 mock 物件

    # 在一個單獨的執行緒中運行，以模擬真實場景
    thread = threading.Thread(target=manager.run_in_background)

    # 模擬 API 伺服器就緒
    api_ready_event.set()
    thread.start()
    thread.join(timeout=5) # 等待執行緒完成，設定超時以防卡死

    assert not thread.is_alive(), "背景執行緒應在 5 秒內完成"

    # 驗證：觸發了金鑰驗證
    mock_requests_post.assert_called_once()
    call_url = mock_requests_post.call_args[0][0]
    assert f"http://127.0.0.1:{api_port}/api/keys/validate" in call_url

    # 驗證：建立了就緒信號檔案
    mock_signal_file.touch.assert_called_once()
    mock_signal_file.write_text.assert_not_called() # 不應寫入錯誤訊息

def test_run_in_background_api_timeout(mock_requests_post, mock_signal_file):
    """
    測試：當 API 伺服器就緒超時，不應執行任何操作。
    """
    api_port = 8000
    # 使用一個永遠不會被設定的事件來模擬超時
    api_ready_event = threading.Event()

    # 縮短 wait 的超時時間以便測試
    with patch.object(api_ready_event, 'wait', return_value=False) as mock_wait:
        manager = ReadinessManager(api_port, api_ready_event)
        manager.readiness_signal_file = mock_signal_file

        manager.run_in_background()

        # 驗證 wait 被以 60 秒的超時呼叫
        mock_wait.assert_called_with(timeout=60)

    # 驗證：未觸發金鑰驗證
    mock_requests_post.assert_not_called()
    # 驗證：未建立信號檔案
    mock_signal_file.touch.assert_not_called()

def test_run_in_background_validation_fails(mock_requests_post, mock_signal_file):
    """
    測試：當觸發金鑰驗證失敗時，仍應建立帶有錯誤訊息的信號檔案。
    """
    api_port = 8000
    api_ready_event = threading.Event()

    # 設定 mock post 以引發錯誤
    mock_requests_post.side_effect = requests.exceptions.RequestException("Connection failed")

    manager = ReadinessManager(api_port, api_ready_event)
    manager.readiness_signal_file = mock_signal_file # 替換為 mock 物件

    thread = threading.Thread(target=manager.run_in_background)

    api_ready_event.set()
    thread.start()
    thread.join(timeout=5)

    assert not thread.is_alive()

    # 驗證：仍然嘗試了觸發金鑰驗證
    mock_requests_post.assert_called_once()

    # 驗證：雖然驗證失敗，但最終還是建立了就緒信號（這裡是為了讓前端知道發生了錯誤）
    # 根據 ReadinessManager 中的邏輯，它會呼叫 _signal_full_readiness
    mock_signal_file.touch.assert_called_once()
