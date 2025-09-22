import pytest
import subprocess
import time
import json
import re
from playwright.sync_api import sync_playwright, Page, expect

# --- 常數 ---
SCREENSHOT_PATH = "tests/processor_update_verification.jpg"

# --- 測試資料 ---
MOCK_FILE_ID = 101
MOCK_PENDING_FILE = {
    "id": MOCK_FILE_ID,
    "url": "mock://file.docx",
    "filename": "mock_document_for_processing.docx"
}

MOCK_TERMINAL_FILE = {
    "id": MOCK_FILE_ID,
    "url": "mock://file.docx",
    "filename": "mock_document_for_processing.docx",
    "status": "processed",
    "status_message": "處理成功"
}

MOCK_WEBSOCKET_PAYLOAD = {
    "type": "task_update",
    "task_type": "processing",
    "task_id": str(MOCK_FILE_ID),
    "status": "processed",
    "result": MOCK_TERMINAL_FILE
}


@pytest.fixture(scope="module")
def server_details():
    """
    在背景啟動 FastAPI 伺服器，解析其輸出的埠號，
    並在測試結束後關閉伺服器。
    """
    print("\n啟動 FastAPI 伺服器 (for processor test)...")
    process = subprocess.Popen(
        ["python", "-u", "src/core/orchestrator.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8'
    )

    port = None
    start_time = time.time()
    timeout_seconds = 60

    for line in iter(process.stdout.readline, ''):
        print(line, end='')
        match = re.search(r"Uvicorn running on .+:(\d+)", line)
        if match and '[api_server' in line:
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

def test_processor_status_update_via_websocket(server_details):
    """
    端對端測試 `page3` 的自動更新功能:
    1. 載入頁面，攔截 API 呼叫以提供一個「待處理」的檔案。
    2. 模擬 WebSocket 訊息推送。
    3. 驗證推送觸發了列表的重新整理。
    4. 攔截第二次 API 呼叫，回傳更新後的狀態。
    5. 驗證檔案卡片從「待處理」區塊移動到「已處理」區塊，且狀態更新。
    """
    port = server_details["port"]
    base_url = f"http://127.0.0.1:{port}"
    processor_page_url = f"{base_url}/page3"
    pending_api_url = "**/api/processor/completed_files"
    terminal_api_url = "**/api/processor/terminal_files"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        page.add_init_script("""
            const originalWebSocket = window.WebSocket;
            window.WebSocket = function(...args) {
                const socket = new originalWebSocket(...args);
                window.mockSocket = socket;
                return socket;
            };
        """)

        # 初始攔截：待處理區有資料，已處理區為空
        page.route(pending_api_url, lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps([MOCK_PENDING_FILE])
        ), times=1)
        page.route(terminal_api_url, lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps([])
        ), times=1)

        try:
            print(f"導航至頁面: {processor_page_url}")
            page.goto(processor_page_url, wait_until="networkidle")

            pending_card_locator = page.locator(f"#pending-cards-container .file-card[data-id='{MOCK_FILE_ID}']")
            terminal_card_locator = page.locator(f"#terminal-cards-container .file-card[data-id='{MOCK_FILE_ID}']")

            print("等待初始卡片出現在「待處理」區...")
            expect(pending_card_locator).to_be_visible(timeout=10000)
            expect(terminal_card_locator).not_to_be_visible()
            print("✅ 初始狀態驗證成功。")

            # 設定第二次 API 呼叫的攔截：待處理區變空，已處理區有資料
            print("設定第二次 API 呼叫的攔截...")
            page.route(pending_api_url, lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps([])
            ), times=1)
            page.route(terminal_api_url, lambda route: route.fulfill(
                status=200, content_type="application/json", body=json.dumps([MOCK_TERMINAL_FILE])
            ), times=1)

            print("模擬 WebSocket 訊息推送...")
            page.evaluate(f"""
                if (window.mockSocket && typeof window.mockSocket.onmessage === 'function') {{
                    const mockEvent = {{ data: JSON.stringify({json.dumps(MOCK_WEBSOCKET_PAYLOAD)}) }};
                    window.mockSocket.onmessage(mockEvent);
                }}
            """)

            print("等待 UI 更新...")
            expect(pending_card_locator).not_to_be_visible(timeout=5000)
            print("✅ 舊卡片已從「待處理」區移除。")

            expect(terminal_card_locator).to_be_visible(timeout=5000)
            print("✅ 新卡片已出現在「已處理」區。")

            updated_status_locator = terminal_card_locator.locator(".status-badge")
            expect(updated_status_locator).to_have_text("✅ 處理成功")
            print("✅ 狀態更新為「處理成功」驗證成功！")

            print(f"擷取螢幕截圖至: {SCREENSHOT_PATH}")
            page.screenshot(path=SCREENSHOT_PATH, type="jpeg", quality=95)
            print("✅ 測試成功完成。")

        except Exception as e:
            page.screenshot(path="tests/error_screenshot_page3.jpg", type="jpeg", quality=95)
            pytest.fail(f"Playwright 測試 (page3) 執行失敗: {e}")

        finally:
            browser.close()
