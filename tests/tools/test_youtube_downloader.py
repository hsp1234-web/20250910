import sys
import pytest
from pathlib import Path

# 將專案根目錄加入到 Python 路徑中
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.tools.youtube_downloader import download_media

# --- 測試設定 ---
# 這個 URL 指向一個已知的、會導致 yt-dlp 掛起的超長直播流存檔
PROBLEM_URL = "https://www.youtube.com/live/G7_taniMyPE"

@pytest.mark.timeout(80) # pytest 的超時應略長於 downloader 的內部超時
def test_download_long_live_stream_handles_timeout_gracefully(tmp_path):
    """
    測試案例：驗證下載器在處理有問題的超長直播流時，
    能夠遵循使用者要求的 65 秒超時限制，並優雅地失敗。

    這個測試會：
    1. 呼叫 download_media 函式嘗試下載有問題的 URL。
    2. 驗證函式是否在約 65 秒後，因為內部設定的超時而拋出一個 RuntimeError。
    3. 驗證拋出的錯誤訊息是否包含了對使用者友善的提示。
    """
    output_dir = tmp_path / "downloads"
    output_dir.mkdir()

    print(f"\n[測試] 測試有問題的 URL: {PROBLEM_URL}")
    print(f"[測試] 輸出目錄: {output_dir}")

    # 期望函式會拋出一個 RuntimeError
    with pytest.raises(RuntimeError) as excinfo:
        download_media(
            youtube_url=PROBLEM_URL,
            output_dir=output_dir,
            download_type="audio",
            raise_exceptions=True # 確保函式在出錯時會拋出異常
        )

    # 驗證錯誤訊息的內容
    error_message = str(excinfo.value)
    assert "下載超時" in error_message
    assert "超長直播存檔" in error_message

    print(f"\n[測試成功] 成功捕捉到預期的超時錯誤，並驗證了錯誤訊息。")
    print(f"錯誤詳情: {error_message}")