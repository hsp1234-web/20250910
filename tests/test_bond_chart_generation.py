# tests/test_bond_chart_generation.py

import pytest
import requests

# 從既有的測試檔案中匯入 fixture
# 雖然最好的做法是將 fixture 移至 conftest.py，但為了快速完成任務，暫時直接匯入
from test_bond_service_startup import bond_service

@pytest.mark.timeout(180) # 給予更長的超時，因為這包含了資料抓取和圖表生成
def test_get_chart_image_endpoint(bond_service):
    """
    測試 /chart/{indicator_id} 端點是否能成功生成並回傳一張圖片。
    """
    indicator = "gdp" # 我們以 gdp 作為測試案例

    # --- 步驟 1: 觸發資料抓取，確保服務中有資料 ---
    fetch_url = f"{bond_service}/fetch/{indicator}"
    print(f"\n[測試步驟 1/3] 正在向 {fetch_url} 觸發資料抓取...")

    try:
        fetch_response = requests.post(fetch_url, timeout=120) # 抓取外部資料可能耗時較久
        # 檢查是否成功觸發
        assert fetch_response.status_code == 200, f"預期 fetch 端點回傳 200，但收到 {fetch_response.status_code}。錯誤: {fetch_response.text}"
        print("資料抓取觸發成功。")
    except requests.exceptions.RequestException as e:
        pytest.fail(f"觸發資料抓取時發生網路錯誤: {e}")

    # --- 步驟 2: 請求圖表圖片 ---
    chart_url = f"{bond_service}/chart/{indicator}"
    print(f"[測試步驟 2/3] 正在向 {chart_url} 請求圖表圖片...")

    try:
        chart_response = requests.get(chart_url, timeout=30)
    except requests.exceptions.RequestException as e:
        pytest.fail(f"請求圖表圖片時發生網路錯誤: {e}")

    # --- 步驟 3: 驗證回應 ---
    print("[測試步驟 3/3] 正在驗證圖表回應...")
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

    print("✅ 圖表生成與 API 端點測試成功！")
