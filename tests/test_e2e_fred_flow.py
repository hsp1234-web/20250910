import pytest
import subprocess
import time
import re
import os
from playwright.sync_api import sync_playwright, Page, expect

# --- 常數 ---
USER_PROVIDED_KEY = "c85a224a0e0d72a7bccb471c0021eb7b"
SCREENSHOT_PATH = "test_results/fred_flow_verification.jpg"

@pytest.fixture(scope="module")
def server_details():
    """
    在背景啟動 FastAPI 伺服器 (透過協調器)，並在測試結束後關閉。
    這個 fixture 會將使用者提供的金鑰設定為環境變數，以供初始啟動使用。
    """
    print("\n為測試準備一個乾淨的環境...")
    key_db_path = "services/key_service/key_service.db"
    if os.path.exists(key_db_path):
        os.remove(key_db_path)
        print(f"✅ 移除了舊的測試資料庫: {key_db_path}")

    print("啟動 FastAPI 伺服器 (for FRED E2E flow test)...")

    # 我們不在此處設定金鑰，因為測試流程的一部分就是要透過 UI 輸入金鑰。
    # 啟動一個乾淨的、沒有預設金鑰的環境。
    test_env = os.environ.copy()
    if "FRED_API_KEY" in test_env:
        del test_env["FRED_API_KEY"]

    process = subprocess.Popen(
        ["python", "-u", "src/core/orchestrator.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        env=test_env
    )

    port = None
    start_time = time.time()
    timeout_seconds = 180 # 增加超時時間

    print("等待伺服器日誌...")
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        match = re.search(r"Uvicorn running on .+:(\d+)", line)
        if match and '[api_server' in line:
            port = int(match.group(1))
            print(f"\n✅ 成功偵測到 API 伺服器埠號: {port}")

        if "核心服務準備完畢！發送『完全就緒』信號" in line:
            print(f"\n✅ 偵測到服務完全就緒信號！")
            break

        if time.time() - start_time > timeout_seconds:
            break

    if port is None:
        process.terminate()
        stdout, _ = process.communicate()
        pytest.fail(f"伺服器啟動失敗或在 {timeout_seconds} 秒內無法偵測到埠號或就緒信號。\n伺服器輸出:\n{stdout}")

    yield {"port": port}

    print("\n關閉 FastAPI 伺服器...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        print("伺服器被強制關閉。")

def test_fred_key_and_chart_flow(server_details):
    """
    測試完整的 FRED 金鑰到圖表流程：
    1. 訪問金鑰管理頁面，確認金鑰未設定。
    2. 輸入並儲存有效的 FRED API 金鑰。
    3. 確認金鑰狀態變為「已設定」。
    4. 導覽至分析儀表板。
    5. 點擊「開始分析」。
    6. 等待一個關鍵圖表（例如綜合壓力指數）成功載入。
    7. 截取圖表元素的螢幕快照 (JPG) 以供驗證。
    """
    port = server_details["port"]
    key_management_url = f"http://127.0.0.1:{port}/primary_dealer_key_management"
    dashboard_url = f"http://127.0.0.1:{port}/primary_dealer_analysis"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_viewport_size({"width": 1600, "height": 1200})

        try:
            # --- 步驟 1 & 2: 輸入並儲存金鑰 ---
            print(f"導航至金鑰管理頁面: {key_management_url}")
            page.goto(key_management_url, wait_until="networkidle", timeout=60000)

            status_div = page.locator("#key-status")
            expect(status_div).to_contain_text("尚未設定 FRED API 金鑰", timeout=15000)
            print("✅ 確認初始金鑰狀態為「尚未設定」。")

            print(f"輸入 API 金鑰...")
            page.locator("#fred-api-key-input").fill(USER_PROVIDED_KEY)
            page.locator("#save-key-btn").click()

            # --- 步驟 3: 確認金鑰儲存成功 ---
            # 等待儲存成功的訊息出現
            expect(status_div).to_contain_text("金鑰已成功儲存", timeout=15000)
            print("✅ 確認金鑰已成功儲存。")

            # 重新整理頁面，再次檢查狀態
            page.reload(wait_until="networkidle")
            expect(status_div).to_contain_text("FRED API 金鑰已設定", timeout=15000)
            print("✅ 重新整理後，確認金鑰狀態為「已設定」。")

            # --- 步驟 4, 5 & 6: 導覽至儀表板並生成圖表 ---
            print(f"導航至分析儀表板: {dashboard_url}")
            page.goto(dashboard_url, wait_until="networkidle", timeout=60000)

            print("點擊「開始分析」按鈕...")
            page.locator("#update-charts-btn").click()

            # 等待一個關鍵圖表容器，並確認其內部不再是 placeholder
            chart_container = page.locator("#chart-container-stress_index")

            print("等待「綜合壓力指數」圖表渲染完成...")
            # 增加超時時間，因為數據計算和渲染可能需要時間
            # 修正：前端會將 plotly 圖表轉換為 <img>，所以我們應該等待圖片元素
            expect(chart_container.locator("img")).to_be_visible(timeout=90000)
            print("✅ 偵測到圖表圖片，驗證通過。")

            # --- 步驟 7: 截取圖表螢幕快照 ---
            print(f"擷取圖表螢幕截圖至: {SCREENSHOT_PATH}")
            chart_container.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=95)
            assert os.path.exists(SCREENSHOT_PATH), "螢幕截圖檔案未被建立！"
            print(f"✅ 成功儲存圖表截圖。測試完成。")

        except Exception as e:
            page.screenshot(path="test_results/fred_flow_error.jpg", full_page=True, type="jpeg", quality=95)
            pytest.fail(f"Playwright FRED 流程測試執行失敗: {e}")

        finally:
            browser.close()