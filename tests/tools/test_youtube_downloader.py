import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.tools.youtube_downloader import download_media

# (Jules @ 2025-10-18) 更新：模擬檔名現在包含繁體中文，以匹配新的檔名規則。
MOCK_YT_DLP_SHORTS_OUTPUT = {
    "id": "xmqS_qC6iE8",
    "title": "安賽龍苦戰三局逆轉昆拉武特",
    "formats": [],
    "thumbnails": [],
    "requested_downloads": [
        {
            "filepath": "downloads/audio/[m4a]安賽龍苦戰三局逆轉昆拉武特.m4a",
            "_filename": "downloads/audio/[m4a]安賽龍苦戰三局逆轉昆拉武特.webm",
            "__finaldir": "downloads/audio",
            "ext": "m4a",
        }
    ],
    "_filename": "downloads/audio/[m4a]安賽龍苦戰三局逆轉昆拉武特.webm",
}

MOCK_YT_DLP_REGULAR_OUTPUT = {
    "id": "regular_video_id",
    "title": "一個常規的中文影片標題",
    "formats": [],
    "thumbnails": [],
    "filepath": "downloads/audio/[m4a]一個常規的中文影片標題.m4a",
    "_filename": "downloads/audio/[m4a]一個常規的中文影片標題.webm",
}


@pytest.fixture
def temp_audio_dir(tmp_path):
    """建立一個臨時的音訊下載目錄"""
    audio_dir = tmp_path / "downloads" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    return audio_dir


def test_download_media_shorts_video_success(temp_audio_dir, mocker):
    """
    測試：當下載 YouTube Shorts 時，應能從 'requested_downloads' 正確解析路徑。
    """
    # 安排 (Arrange)
    url = "https://youtube.com/shorts/xmqS_qC6iE8"
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(MOCK_YT_DLP_SHORTS_OUTPUT)
    mock_result.returncode = 0

    mocker.patch("subprocess.run", return_value=mock_result)

    # 建立一個假的目標檔案，讓 Path.exists() 通過
    expected_path_str = MOCK_YT_DLP_SHORTS_OUTPUT["requested_downloads"][0]["filepath"]
    # 我們需要確保測試環境中的路徑與模擬輸出的路徑一致
    final_file_path = temp_audio_dir.parent.parent / expected_path_str
    final_file_path.parent.mkdir(parents=True, exist_ok=True)
    final_file_path.touch()

    # 使用 mocker 來模擬 Path.exists()
    mocker.patch.object(Path, 'exists', return_value=True)

    # 攔截 print() 呼叫以捕獲輸出
    mock_print = mocker.patch("builtins.print")

    # 行動 (Act)
    # 呼叫被測函式，並設定 raise_exceptions=True 以便在測試中捕獲錯誤
    download_media(
        youtube_url=url,
        output_dir=temp_audio_dir,
        download_type="audio",
        audio_format="m4a",
        raise_exceptions=True # 在測試中拋出異常而不是 sys.exit
    )

    # 斷言 (Assert)
    # 1. 驗證 subprocess.run 是否被正確呼叫
    subprocess.run.assert_called_once()

    # 2. 驗證函式是否正確解析了 'requested_downloads' 中的路徑並輸出
    mock_print.assert_called_once()
    output_json = json.loads(mock_print.call_args[0][0])

    assert output_json["status"] == "已完成"
    assert output_json["output_path"] == expected_path_str
    assert output_json["video_title"] == "安賽龍苦戰三局逆轉昆拉武特"


def test_download_media_regular_video_success(temp_audio_dir, mocker):
    """
    測試：當下載一般影片時，應能從頂層 'filepath' 正確解析路徑。
    """
    # 安排 (Arrange)
    url = "https://youtube.com/watch?v=regular_video_id"
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(MOCK_YT_DLP_REGULAR_OUTPUT)
    mock_result.returncode = 0

    mocker.patch("subprocess.run", return_value=mock_result)

    expected_path_str = MOCK_YT_DLP_REGULAR_OUTPUT["filepath"]
    final_file_path = temp_audio_dir.parent.parent / expected_path_str
    final_file_path.parent.mkdir(parents=True, exist_ok=True)
    final_file_path.touch()

    mocker.patch.object(Path, 'exists', return_value=True)
    mock_print = mocker.patch("builtins.print")

    # 行動 (Act)
    download_media(
        youtube_url=url,
        output_dir=temp_audio_dir,
        raise_exceptions=True
    )

    # 斷言 (Assert)
    subprocess.run.assert_called_once()
    mock_print.assert_called_once()
    output_json = json.loads(mock_print.call_args[0][0])

    assert output_json["status"] == "已完成"
    assert output_json["output_path"] == expected_path_str
    assert output_json["video_title"] == "一個常規的中文影片標題"


def test_download_media_file_not_found_error(temp_audio_dir, mocker):
    """
    測試：當最終檔案不存在時，應拋出 FileNotFoundError。
    """
    # 安排 (Arrange)
    url = "https://youtube.com/shorts/xmqS_qC6iE8"
    mock_result = MagicMock()
    mock_result.stdout = json.dumps(MOCK_YT_DLP_SHORTS_OUTPUT)
    mock_result.returncode = 0

    mocker.patch("subprocess.run", return_value=mock_result)

    # 這次不建立假檔案，所以 Path.exists() 會回傳 False
    mocker.patch.object(Path, 'exists', return_value=False)

    # 行動 & 斷言
    with pytest.raises(FileNotFoundError, match="yt-dlp 處理完成後，無法在指定路徑找到檔案"):
        download_media(
            youtube_url=url,
            output_dir=temp_audio_dir,
            raise_exceptions=True
        )