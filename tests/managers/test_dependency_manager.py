# tests/managers/test_dependency_manager.py
import pytest
import subprocess
from unittest.mock import patch, MagicMock

# 為了讓測試能找到 `core` 模組
import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / 'src'))

from core.managers.dependency_manager import DependencyManager

@pytest.fixture
def mock_subprocess_run():
    """模擬 subprocess.run 函式。"""
    with patch('subprocess.run') as mock_run:
        # 預設模擬一個成功的執行結果，且沒有缺失的套件
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        yield mock_run

def test_setup_core_dependencies_all_present(mock_subprocess_run):
    """
    測試：當所有核心依賴都已存在時，不應執行安裝。
    """
    manager = DependencyManager()
    manager.setup_core_dependencies()

    # 驗證：subprocess.run 只被呼叫了一次（用於檢查）
    assert mock_subprocess_run.call_count == 1

    # 驗證該次呼叫是執行 check_deps.py
    first_call_args, _ = mock_subprocess_run.call_args
    command_list = first_call_args[0]
    assert "check_deps.py" in " ".join(command_list)


def test_setup_core_dependencies_installs_missing(mock_subprocess_run):
    """
    測試：當偵測到缺失套件時，應觸發安裝。
    """
    # 設定：第一次呼叫（檢查）回傳有缺失的套件，後續呼叫（安裝）正常執行
    # 我們需要模擬兩次 subprocess.run 的行為
    mock_check_result = MagicMock(returncode=0, stdout="requests\nfastapi", stderr="")
    mock_install_result = MagicMock(returncode=0, stdout="Successfully installed", stderr="")

    # side_effect 列表會讓每次呼叫 mock 時，依序返回列表中的項目
    mock_subprocess_run.side_effect = [
        mock_check_result,    # 第一次呼叫 (check_deps.py) 的回傳值
        mock_install_result,  # 第二次呼叫 (uv install) 的回傳值
        mock_install_result   # 為 pip fallback 準備的第三個可能的回傳值
    ]

    manager = DependencyManager()
    manager.setup_core_dependencies()

    # 驗證：subprocess.run 至少被呼叫兩次（檢查 + uv 安裝）
    assert mock_subprocess_run.call_count >= 2

    # 驗證第二次呼叫是安裝命令
    second_call_args, _ = mock_subprocess_run.call_args_list[1]
    command_list = second_call_args[0]

    assert "install" in " ".join(command_list)
    assert "requests" in " ".join(command_list)
    assert "fastapi" in " ".join(command_list)

def test_install_falls_back_to_pip(mock_subprocess_run):
    """
    測試：當 uv 安裝失敗時，是否會自動退回使用 pip。
    """
    # 設定：模擬 check_deps.py 找到缺失套件，然後 uv 安裝失敗，最後 pip 安裝成功
    mock_check_result = MagicMock(returncode=0, stdout="requests", stderr="")
    mock_uv_fail_result = FileNotFoundError("uv not found") # 模擬 uv 不存在
    mock_pip_success_result = MagicMock(returncode=0, stdout="Successfully installed with pip", stderr="")

    # 這裡我們需要 patch subprocess.run，讓它在特定情況下拋出錯誤
    def subprocess_side_effect(*args, **kwargs):
        command = args[0]
        if "check_deps.py" in " ".join(command):
            return mock_check_result
        elif "uv" in " ".join(command):
            raise mock_uv_fail_result
        elif "pip" in " ".join(command):
            return mock_pip_success_result
        return MagicMock(returncode=1) # 預設失敗

    mock_subprocess_run.side_effect = subprocess_side_effect

    manager = DependencyManager()
    manager.setup_core_dependencies()

    # 驗證：subprocess.run 應該被呼叫三次 (check, uv, pip)
    assert mock_subprocess_run.call_count == 3

    # 驗證最後一次呼叫是 pip
    last_call_args, _ = mock_subprocess_run.call_args
    last_command = last_call_args[0]
    assert "pip" in " ".join(last_command)
    assert "uv" not in " ".join(last_command)
