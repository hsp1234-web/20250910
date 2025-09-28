import pytest
import subprocess
import time
import re
import os
from playwright.sync_api import sync_playwright, Page, expect

# --- 常數 ---
SCREENSHOT_PATH = "test_results/dashboard_verification.jpg"

@pytest.fixture(scope="module")
def server_details():
    """
    在背景啟動 FastAPI 伺服器 (透過協調器)，解析其輸出的埠號，
    並在測試結束後關閉伺服器。
    """
    print("\n啟動 FastAPI 伺服器 (for dashboard test)...")

    # 為了讓測試能夠獨立運行，在此處手動設定測試用的環境變數
    test_env = os.environ.copy()
    test_env["FRED_API_KEY"] = "77b0a570c6a17007e4f5af229c2aecc9"

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
    # 增加超時時間，因為第一次啟動可能需要安裝依賴
    timeout_seconds = 180

    print("等待伺服器日誌...")
    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        # 我們需要 API Server 的埠號
        match = re.search(r"Uvicorn running on .+:(\d+)", line)
        if match and '[api_server' in line:
            port = int(match.group(1))
            print(f"\n✅ 成功偵測到 API 伺服器埠號: {port}")
            # 即使找到埠號，也繼續等待完全就緒信號

        # 等待協調器發出的「完全就緒」信號
        if "核心服務準備完畢！發送『完全就緒』信號" in line:
            print(f"\n✅ 偵測到服務完全就緒信號！")
            break

        if time.time() - start_time > timeout_seconds:
            break

    if port is None:
        process.terminate()
        stdout, _ = process.communicate()
        print("無法從伺服器輸出中找到埠號。伺服器輸出:\n", stdout)
        pytest.fail(f"伺服器啟動失敗或在 {timeout_seconds} 秒內無法偵測到埠號或就緒信號。")

    yield {"port": port}

    print("\n關閉 FastAPI 伺服器...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        print("伺服器被強制關閉。")

def test_dashboard_charts_are_visible(server_details):
    """
    端對端測試儀表板頁面：
    1. 載入頁面。
    2. 等待一個關鍵圖表（例如壓力指數 MACD）的圖片被渲染出來。
    3. 截取整個頁面的螢幕快照以供人工驗證。
    """
    port = server_details["port"]
    dashboard_url = f"http://127.0.0.1:{port}/primary_dealer_analysis"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # 增加頁面視窗大小以確保所有圖表都在可視範圍內
        page.set_viewport_size({"width": 1920, "height": 1600})

        try:
            print(f"導航至儀表板頁面: {dashboard_url}")
            page.goto(dashboard_url, wait_until="networkidle", timeout=60000)

            # 等待一個比較後面載入的圖表容器，並確認其內部不再是 placeholder
            # 我們檢查它是否包含一個 <img> 標籤，這表示 Plotly 圖表已成功轉換為圖片
            last_chart_container = page.locator("#chart-container-stress_index_macd")

            print("等待壓力指數 MACD 圖表渲染完成...")
            # 增加超時時間，因為數據計算和渲染可能需要時間
            expect(last_chart_container.locator("img")).to_be_visible(timeout=90000)
            print("✅ 偵測到圖表圖片，驗證通過。")

            # 額外驗證：確保頁面上沒有載入失敗的錯誤訊息
            error_placeholder = page.locator(".placeholder:has-text('失敗')")
            count = error_placeholder.count()
            assert count == 0, f"頁面上發現了 {count} 個載入失敗的圖表！"
            print("✅ 確認頁面上沒有顯示「載入失敗」的圖表。")

            print(f"擷取螢幕截圖至: {SCREENSHOT_PATH}")
            page.screenshot(path=SCREENSHOT_PATH, full_page=True, type="jpeg", quality=95)
            print("✅ 測試成功完成。")

        except Exception as e:
            # 發生錯誤時也截圖，以便除錯
            page.screenshot(path="test_results/dashboard_error.jpg", full_page=True, type="jpeg", quality=95)
            pytest.fail(f"Playwright 儀表板測試執行失敗: {e}")

        finally:
            browser.close()