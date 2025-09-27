# tests/test_bond_chart_generation.py

import pytest
import requests
import os

# 確保我們有 API 金鑰，否則跳過測試
FRED_API_KEY = os.getenv("FRED_API_KEY")
pytestmark = pytest.mark.skipif(not FRED_API_KEY, reason="需要設定 FRED_API_KEY 環境變數以執行整合測試")

# 從既有的測試檔案中匯入 fixture
# 雖然最好的做法是將 fixture 移至 conftest.py，但為了快速完成任務，暫時直接匯入
try:
    from .test_bond_service_startup import bond_service
except ImportError:
    from test_bond_service_startup import bond_service


@pytest.mark.timeout(180) # 給予更長的超時，因為這包含了資料抓取和圖表生成
@pytest.mark.parametrize("indicator", ["sofr"])
def test_get_chart_image_endpoint(bond_service, indicator):
    """
    測試 /chart/{indicator_id} 端點是否能成功生成並回傳一張圖片。
    這個測試會對 'sofr' 指標進行測試，以驗證 OpenBB 的整合。
    """
    print(f"\n--- 開始測試指標: {indicator.upper()} (使用 OpenBB) ---")

    # --- 步驟 1: 觸發資料抓取，確保服務中有資料 ---
    fetch_url = f"{bond_service}/fetch/{indicator}"
    print(f"[{indicator.upper()}] [步驟 1/3] 正在向 {fetch_url} 觸發資料抓取...")

    try:
        fetch_response = requests.post(fetch_url, timeout=120) # 抓取外部資料可能耗時較久
        # 檢查是否成功觸發
        assert fetch_response.status_code == 200, f"預期 fetch 端點回傳 200，但收到 {fetch_response.status_code}。錯誤: {fetch_response.text}"
        print(f"[{indicator.upper()}] 資料抓取觸發成功。")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"觸發資料抓取時發生網路錯誤: {e}")

    # --- 步驟 2: 請求圖表圖片 ---
    # 增加日期範圍參數以測試我們之前的修復
    chart_url = f"{bond_service}/chart/{indicator}?start_date=2023-01-01&end_date=2023-12-31"
    print(f"[{indicator.upper()}] [步驟 2/3] 正在向 {chart_url} 請求圖表圖片...")

    try:
        chart_response = requests.get(chart_url, timeout=30)
    except requests.exceptions.RequestException as e:
        pytest.fail(f"請求圖表圖片時發生網路錯誤: {e}")

    # --- 步驟 3: 驗證回應 ---
    print(f"[{indicator.upper()}] [步驟 3/3] 正在驗證圖表回應...")
    # 3a. 驗證狀態碼
    assert chart_response.status_code == 200, f"預期圖表端點回傳 200，但收到 {chart_response.status_code}。錯誤: {chart_response.text}"

    # 3b. 驗證 Content-Type
    content_type = chart_response.headers.get("Content-Type")
    assert content_type == "image/jpeg", f"預期的 Content-Type 是 'image/jpeg'，但收到 '{content_type}'"

    # 3c. 驗證回應內容 (圖片)
    image_bytes = chart_response.content
    assert image_bytes is not None, "圖片回應內容不應為空"
    # 一個合理的 JPG 圖片大小應該大於 1KB (1024 bytes)
    assert len(image_bytes) > 1024, f"預期圖片大小應大於 1KB，但實際大小為 {len(image_bytes)} bytes"

    # 3d. (可選) 驗證圖片開頭是否為 JPG 的魔術數字
    # JPG/JPEG 檔案通常以 FF D8 FF 開頭
    assert image_bytes.startswith(b'\xff\xd8\xff'), "回應內容不是一個有效的 JPG 圖片 (未找到 JPG 檔案標頭)"

    print(f"✅ 指標 {indicator.upper()} 的圖表生成與 API 端點測試成功！")