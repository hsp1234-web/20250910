import subprocess
import time
import sys
from playwright.sync_api import sync_playwright, expect, Page

# --- 服務設定 ---
SERVICES = {
    "api_server": {
        "app": "src.api.api_server:app",
        "port": 8001
    },
    "bond_service": {
        "app": "services.bond_data_service.main:app",
        "port": 8002
    },
    "llm_service": {
        "app": "services.llm_service.main:app",
        "port": 8003
    }
}

def start_service(name: str) -> subprocess.Popen:
    """根據名稱啟動一個背景服務。"""
    config = SERVICES[name]
    print(f"🚀 正在啟動服務: {name} (埠號: {config['port']})...")
    command = [
        sys.executable,  # 使用當前的 Python 直譯器
        "-m", "uvicorn",
        config['app'],
        "--host", "0.0.0.0",
        "--port", str(config['port'])
    ]
    # 為每個服務建立一個日誌檔案
    log_file = open(f"{name}_service.log", "w")
    process = subprocess.Popen(
        command,
        cwd=".", # 從專案根目錄執行
        stdout=log_file,
        stderr=log_file,
        text=True
    )
    # 給服務一點時間啟動
    time.sleep(5)
    print(f"✅ 服務 {name} 應該已在運行。")
    return process

def run_tests(page: Page):
    """
    執行端到端測試的核心邏輯。
    """
    base_url = f"http://127.0.0.1:{SERVICES['api_server']['port']}"
    print(f"\n--- 🧪 開始執行測試 ---")
    print(f"導航到主頁: {base_url}")

    # 1. 導航到主頁並驗證
    page.goto(base_url, wait_until="networkidle")
    # 驗證標題是否正確
    expect(page).to_have_title("鳳凰主頁")
    print("✅ 主頁載入成功，標題正確。")

    # 2. 獲取所有可見的連結
    # 我們只關心導向到相對路徑的連結，排除外部連結
    links = page.locator('a[href^="/"], a[href^="./"], a[href^="#"]').all()
    hrefs = [link.get_attribute("href") for link in links]
    # 過濾掉重複和無效的連結
    unique_hrefs = sorted(list(set(href for href in hrefs if href and href != '#')))

    print(f"🔍 在主頁上發現 {len(unique_hrefs)} 個唯一的內部連結。準備進行遍歷測試...")
    print(f"  -> 連結列表: {unique_hrefs}")

    # 3. 遍歷並點擊每一個連結
    for i, href in enumerate(unique_hrefs):
        print(f"\n[{i+1}/{len(unique_hrefs)}] 正在測試連結: {href}")
        try:
            # 點擊連結並等待頁面載入
            # JULES'S FIX: 使用 CSS locator 來通過 href 屬性定位連結
            page.locator(f'a[href="{href}"]').first.click()
            page.wait_for_load_state("domcontentloaded")

            # 基礎驗證：檢查頁面標題是否包含錯誤訊息
            title = page.title()
            print(f"  -> 頁面 '{href}' 載入成功，標題為: '{title}'")
            if "error" in title.lower() or "not found" in title.lower() or "錯誤" in title:
                print(f"  🚨 警告: 頁面 '{href}' 的標題可能表示一個錯誤。")
            else:
                print(f"  ✅ 頁面 '{href}' 基礎驗證通過。")

        except Exception as e:
            print(f"  ❌ 錯誤: 點擊或載入連結 '{href}' 時發生問題: {e}")

        # 每次點擊後，都返回主頁以開始下一次測試，確保測試的獨立性
        if i < len(unique_hrefs) - 1:
            print("  -> 返回主頁...")
            page.goto(base_url, wait_until="networkidle")

    print("\n--- ✅ 所有連結測試完畢 ---")


def main():
    """
    主函式，負責設定、執行和清理整個測試流程。
    """
    processes = {}
    try:
        # 啟動所有必要的服務
        for name in SERVICES:
            processes[name] = start_service(name)

        # 使用 Playwright 執行測試
        with sync_playwright() as p:
            # 我們可以使用 --headless=False 來觀看測試過程
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            run_tests(page)
            browser.close()

    finally:
        # 確保所有服務都被關閉
        print("\n--- 🧹 正在清理和關閉所有服務 ---")
        for name, process in processes.items():
            if process.poll() is None: # 如果程序還在運行
                print(f"正在終止服務: {name} (PID: {process.pid})...")
                process.terminate()
                process.wait(timeout=5)
                print(f"服務 {name} 已關閉。")

if __name__ == "__main__":
    main()