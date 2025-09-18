# tests/managers/test_process_manager.py
import pytest
import subprocess
import threading
import time
from unittest.mock import patch, MagicMock, mock_open

# 為了讓測試能找到 `core` 模組
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

from core.managers.process_manager import ProcessManager

@pytest.fixture
def mock_popen():
    """模擬 subprocess.Popen，並提供一個可控制的 mock process 物件。"""
    with patch('subprocess.Popen') as mock_popen_class:
        mock_process = MagicMock()
        mock_process.poll.return_value = None # 預設：進程正在運行
        mock_process.pid = 1234

        # 模擬 stdout 流，讓它可以被 readline
        mock_process.stdout.readline.return_value = ""

        mock_popen_class.return_value = mock_process
        yield mock_popen_class

@pytest.fixture
def mock_find_port():
    """模擬 find_free_port，回傳固定的埠號。"""
    with patch('core.managers.process_manager.ProcessManager._find_free_port') as mock_port:
        mock_port.side_effect = [8001, 8002] # db_manager, api_server
        yield mock_port

def test_start_services_launches_processes(mock_popen, mock_find_port):
    """
    測試：start_services 是否能正確啟動 db_manager 和 api_server。
    """
    manager = ProcessManager()

    # 模擬 stream_reader 找到就緒信號
    def readline_side_effect(*args, **kwargs):
        if manager.db_ready_event.is_set(): # 如果 db 好了，就輪到 api
            yield "Uvicorn running on"
        else:
            yield "Application startup complete"
        while True:
            yield "" # 之後都回傳空字串

    mock_popen.return_value.stdout.readline.side_effect = readline_side_effect()

    api_port, api_ready_event = manager.start_services()

    # 驗證：Popen 被呼叫了兩次
    assert mock_popen.call_count == 2

    # 驗證第一次呼叫是 db_manager
    first_call_args, _ = mock_popen.call_args_list[0]
    assert "db.manager:app" in " ".join(first_call_args[0])

    # 驗證第二次呼叫是 api_server
    second_call_args, _ = mock_popen.call_args_list[1]
    assert "api.api_server" in " ".join(second_call_args[0])

    # 驗證事件被設定
    assert manager.db_ready_event.is_set()
    assert api_ready_event.is_set()
    assert api_port == 8002

def test_shutdown_terminates_processes(mock_popen, mock_find_port):
    """
    測試：shutdown 方法是否會優雅地終止所有進程。
    """
    manager = ProcessManager()
    # 假裝啟動了服務
    manager.processes = [mock_popen.return_value, mock_popen.return_value]

    manager.shutdown()

    # 驗證：terminate 被呼叫
    for proc in manager.processes:
        proc.terminate.assert_called_once()
        proc.kill.assert_not_called() # 不應呼叫 kill

def test_shutdown_kills_stubborn_processes(mock_popen, mock_find_port):
    """
    測試：對於無法終止的進程，shutdown 是否會強制 kill。
    """
    manager = ProcessManager()

    # 模擬一個頑固的進程
    stubborn_process = MagicMock()
    stubborn_process.poll.return_value = None # 永遠回傳 None，表示還在運行
    stubborn_process.pid = 5678

    manager.processes = [stubborn_process]

    # 為了測試不等太久，我們 patch time.sleep
    with patch('time.sleep'):
        manager.shutdown()

    # 驗證：terminate 和 kill 都被呼叫了
    stubborn_process.terminate.assert_called_once()
    stubborn_process.kill.assert_called_once()

def test_monitor_raises_on_unexpected_exit(mock_popen, mock_find_port):
    """
    測試：當監控到子進程意外退出時，是否會引發 RuntimeError。
    """
    manager = ProcessManager()

    # 模擬一個會意外退出的進程
    crashed_process = MagicMock()
    crashed_process.poll.return_value = 1 # 非 None 表示已退出
    crashed_process.pid = 9999
    crashed_process.args = ["dummy_command"]

    manager.processes = [crashed_process]

    with pytest.raises(RuntimeError) as excinfo:
        manager.monitor_processes()

    assert "已意外終止" in str(excinfo.value)
    assert "9999" in str(excinfo.value)
