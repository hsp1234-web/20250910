import pytest
import subprocess
import time
import json
import re
from playwright.sync_api import sync_playwright, Page, expect

# --- 常數 ---
SCREENSHOT_PATH = "tests/summary_update_verification.jpg"

# --- 測試資料 ---
MOCK_TASK_ID = 1
MOCK_TASK_INITIAL = {
    "id": MOCK_TASK_ID,
    "title": "四月小作文-精確3162",
    "author": "504-0718103Leo",
    "message_date": "2025-04-04",
    "summary_status": "pending",
    "summary_token_usage": "N/A"
}

MOCK_WEBSOCKET_PAYLOAD = {
    "type": "analysis_update",
    "task_id": MOCK_TASK_ID,
    "result": {
        "id": MOCK_TASK_ID,
        "title": "四月小作文-精確3162",
        "author": "504-0718103Leo",
        "message_date": "2025-04-04",
        "summary_status": "completed",
        "summary_content": "這是由 Playwright 測試腳本模擬產生的摘要內容。",
        "summary_token_usage": 123
    }
}


@pytest.fixture(scope="module")
def server_details():
    """
    在背景啟動 FastAPI 伺服器，解析其輸出的埠號，
    並在測試結束後關閉伺服器。
    """
    print("\n啟動 FastAPI 伺服器...")
    # 使用 orchestrator 啟動，因為這是應用的正確入口點
    process = subprocess.Popen(
        ["python", "-u", "src/core/orchestrator.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # 將 stderr 合併到 stdout 以便解析
        text=True,
        encoding='utf-8'
    )

    port = None
    # 增加超時機制
    start_time = time.time()
    timeout_seconds = 60 # 延長超時時間到 60 秒，因為協調器啟動較慢

    # 從 orchestrator 的日誌中解析出 api_server 的埠號
    for line in iter(process.stdout.readline, ''):
        print(line, end='') # 即時輸出日誌以便除錯

        # 使用更寬鬆的正規表示式來匹配埠號
        match = re.search(r"Uvicorn running on .+:(\d+)", line)
        if match:
            # 我們需要確保這是 API 伺服器的埠號，而不是 db_manager 的
            # 根據日誌，API 伺服器的日誌帶有 [api_server] 或 [api_server_stderr] 前綴
            if '[api_server' in line:
                port = int(match.group(1))
                print(f"\n✅ 成功偵測到 API 伺服器埠號: {port}")
                break

        if time.time() - start_time > timeout_seconds:
            break

    if port is None:
        process.terminate()
        stdout, _ = process.communicate()
        print("無法從伺服器輸出中找到埠號。伺服器輸出:\n", stdout)
        pytest.fail("伺服器啟動失敗或在 60 秒內無法偵測到埠號。")

    yield {"port": port}

    print("\n關閉 FastAPI 伺服器...")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        print("伺服器被強制關閉。")

def test_summary_status_update_via_websocket(server_details):
    """
    端對端測試（V2 - 驗證 fetchTasks 刷新邏輯）：
    1. 載入摘要頁面，攔截初次 API 呼叫以提供「待處理」狀態的資料。
    2. 模擬 WebSocket 訊息推送。
    3. 驗證 WebSocket 推送是否觸發了第二次 API 呼叫。
    4. 攔截第二次 API 呼叫，並回傳「已完成」狀態的資料。
    5. 驗證前端卡片的狀態是否從 '待處理' 更新為 '✅ 已完成'。
    6. 擷取螢幕截圖以供驗證。
    """
    port = server_details["port"]
    base_url = f"http://127.0.0.1:{port}"
    summary_page_url = f"{base_url}/page4_summary_center"
    api_url_pattern = "**/api/analyzer/files_for_summary"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 注入 JS 以便能夠模擬 WebSocket 訊息
        page.add_init_script("""
            const originalWebSocket = window.WebSocket;
            window.WebSocket = function(...args) {
                const socket = new originalWebSocket(...args);
                window.mockSocket = socket;
                return socket;
            };
        """)

        # 初始設定：攔截 API 呼叫並提供初始資料
        page.route(api_url_pattern, lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps([MOCK_TASK_INITIAL])
        ), times=1) # `times=1` 確保這個攔截器只作用一次

        # 也需要攔截金鑰和模型的 API
        page.route("**/api/keys", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps([{"id": 1, "name": "test-key", "is_valid": True}])))
        page.route("**/api/keys/models", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps(["gemini-1.5-flash-mock"])))

        try:
            print(f"導航至頁面: {summary_page_url}")
            page.goto(summary_page_url, wait_until="networkidle")

            card_locator = page.locator(f".file-card[data-task-id='{MOCK_TASK_ID}']")

            print("等待卡片出現...")
            expect(card_locator).to_be_visible(timeout=10000)
            print("卡片已出現。")

            initial_status_locator = card_locator.locator(".status-badge")
            expect(initial_status_locator).to_have_text("待處理")
            print("初始狀態 '待處理' 驗證成功。")

            # 關鍵步驟：在模擬 WebSocket 訊息之前，設定好對第二次 API 呼叫的攔截
            print("設定第二次 API 呼叫的攔截...")
            page.route(api_url_pattern, lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps([MOCK_WEBSOCKET_PAYLOAD['result']]) # 回傳更新後的資料
            ), times=1)

            print("在頁面中執行 JavaScript 以模擬 WebSocket 訊息...")
            page.evaluate(f"""
                if (window.mockSocket && typeof window.mockSocket.onmessage === 'function') {{
                    const mockEvent = {{ data: JSON.stringify({json.dumps(MOCK_WEBSOCKET_PAYLOAD)}) }};
                    window.mockSocket.onmessage(mockEvent);
                    console.log("模擬的 WebSocket 訊息已發送。");
                }} else {{
                    console.error("找不到 mockSocket 或其 onmessage 處理器。");
                }}
            """)

            print("等待狀態更新為 '✅ 已完成'...")
            # 由於 UI 是由第二次 API 呼叫的結果渲染的，我們只需等待 UI 更新即可
            updated_status_locator = card_locator.locator(".status-badge")
            expect(updated_status_locator).to_have_text("✅ 已完成", timeout=5000)
            print("✅ 狀態更新驗證成功！")

            # 驗證其他欄位也已更新
            updated_token_locator = card_locator.locator(".token-usage")
            expect(updated_token_locator).to_have_text("123")
            print("✅ Token 消耗欄位更新驗證成功！")


            print(f"擷取螢幕截圖至: {SCREENSHOT_PATH}")
            page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=95)
            print("✅ 測試成功完成。")

        except Exception as e:
            page.screenshot(path="tests/error_screenshot.jpg", type="jpeg", quality=95)
            pytest.fail(f"Playwright 測試執行失敗: {e}")

        finally:
            browser.close()
