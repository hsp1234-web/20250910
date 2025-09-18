# tests/test_orchestrator_integration.py
import pytest
from unittest.mock import patch, MagicMock, call
import threading

# 為了讓測試能找到 `core` 模組
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

# 必須在 patch 之前導入
from core import orchestrator

@pytest.fixture
def mock_managers():
    """模擬所有的管理器，並回傳它們的 mock 實例。"""
    # 建立 mock 物件
    mock_dep_manager = MagicMock()
    mock_proc_manager = MagicMock()
    mock_read_manager = MagicMock()

    # 設定 mock 物件的行為
    # start_services 需要回傳一個元組 (api_port, api_ready_event)
    mock_proc_manager.start_services.return_value = (8000, threading.Event())

    # 使用 patch 來攔截管理器的實例化過程，並替換為我們的 mock 物件
    with patch('core.orchestrator.DependencyManager', return_value=mock_dep_manager) as mock_dep_class, \
         patch('core.orchestrator.ProcessManager', return_value=mock_proc_manager) as mock_proc_class, \
         patch('core.orchestrator.ReadinessManager', return_value=mock_read_manager) as mock_read_class, \
         patch('threading.Thread') as mock_thread_class: # 也模擬執行緒

        yield {
            "dep_manager": mock_dep_manager,
            "proc_manager": mock_proc_manager,
            "read_manager": mock_read_manager,
            "thread_class": mock_thread_class
        }

def test_orchestrator_main_flow_and_shutdown_on_success(mock_managers):
    """
    測試 orchestrator.main 在成功執行時的正常流程。
    """
    mock_proc_manager = mock_managers["proc_manager"]
    # 模擬 monitor_processes 正常結束 (例如，收到一個停止信號)
    mock_proc_manager.monitor_processes.return_value = None

    with patch('sys.exit') as mock_exit:
        orchestrator.main()

    # --- 驗證呼叫順序 ---
    dep_manager = mock_managers["dep_manager"]
    proc_manager = mock_managers["proc_manager"]

    # 斷言呼叫順序
    manager = MagicMock()
    manager.attach_mock(dep_manager, 'dep')
    manager.attach_mock(proc_manager, 'proc')

    expected_calls = [
        call.dep.setup_core_dependencies(),
        call.proc.start_services(mock_mode=False),
        call.proc.monitor_processes(),
        call.proc.shutdown()
    ]
    manager.assert_has_calls(expected_calls, any_order=False)

    # 驗證 ReadinessManager 的執行緒有被啟動
    mock_managers["thread_class"].assert_called_once()

    # 驗證最終以狀態 0 退出
    mock_exit.assert_called_once_with(0)


def test_orchestrator_shutdown_on_exception(mock_managers):
    """
    測試 orchestrator.main 在執行過程中發生錯誤時，是否仍能保證 shutdown 被呼叫。
    """
    mock_proc_manager = mock_managers["proc_manager"]
    # 模擬 monitor_processes 引發一個非預期的錯誤
    mock_proc_manager.monitor_processes.side_effect = RuntimeError("子程序意外崩潰")

    with patch('sys.exit') as mock_exit:
        # 我們預期這個錯誤會被捕獲，然後執行 finally 區塊
        orchestrator.main()

    # --- 驗證 ---
    # 即使發生了錯誤，shutdown 也必須在 finally 區塊中被呼叫
    mock_proc_manager.shutdown.assert_called_once()

    # 驗證最終以狀態 1 退出
    mock_exit.assert_called_once_with(1)
