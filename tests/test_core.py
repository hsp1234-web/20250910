# tests/test_core.py
import pytest
import sys
from pathlib import Path
from freezegun import freeze_time

# --- 路徑修正，確保可以從 src 匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from core.time_utils import get_current_taipei_time_iso, format_iso_for_filename

# 使用 freezegun 來固定當前時間，讓測試結果可預測
# 我們選擇一個 UTC 時間
@freeze_time("2025-09-12 10:00:00") # freezegun 預設將此視為 UTC
def test_get_current_taipei_time_iso():
    """
    測試 get_current_taipei_time_iso 是否能正確回傳當前的台北時間 ISO 字串。
    UTC 2025-09-12 10:00:00 應等於台北時間 2025-09-12 18:00:00+08:00
    """
    expected_iso = "2025-09-12T18:00:00+08:00"
    assert get_current_taipei_time_iso() == expected_iso

@pytest.mark.parametrize("input_iso, expected_filename_ts", [
    # 1. 標準 UTC 時間字串
    ("2025-09-12T10:00:00Z", "2025-09-12T18-00-00"),
    # 2. 已是台北時區的 ISO 字串
    ("2025-09-12T18:00:00+08:00", "2025-09-12T18-00-00"),
    # 3. 不含時區資訊的 "天真" 時間字串 (應被視為台北時間)
    ("2025-09-12 18:00:00", "2025-09-12T18-00-00"),
    # 4. 另一種常見的 ISO 格式
    ("2025-09-12T10:00:00.123456", "2025-09-12T10-00-00"),
    # 5. 包含毫秒和 Z 的 UTC 時間
    ("2025-01-01T00:00:00.500Z", "2025-01-01T08-00-00"),
    # 6. dateutil 可以解析的純數字日期 (會被當作台北時區的午夜)
    ("20231027", "2023-10-27T00-00-00"),
])
def test_format_iso_for_filename_valid_inputs(input_iso, expected_filename_ts):
    """
    測試 format_iso_for_filename 函式是否能正確處理各種有效的 ISO 字串。
    """
    assert format_iso_for_filename(input_iso) == expected_filename_ts

@freeze_time("2023-10-27 15:00:00")
def test_format_iso_for_filename_invalid_inputs():
    """
    測試 format_iso_for_filename 在收到無效或空字串時，是否能優雅地回退。
    """
    # 預期的回退結果是 "當前" 的台北時間 (UTC 15:00 -> TPE 23:00)
    expected_fallback_ts = "2023-10-27T23-00-00"

    # 1. 空字串
    assert format_iso_for_filename("") == expected_fallback_ts

    # 2. None 值
    assert format_iso_for_filename(None) == expected_fallback_ts

    # 3. 無法解析的亂碼
    assert format_iso_for_filename("這不是時間") == expected_fallback_ts
