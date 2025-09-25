import httpx
import subprocess
import time
import json
import os

# --- 設定 ---
SERVER_URL = "http://127.0.0.1:3025"
BOND_SERVICE_DIR = "services/bond_data_service" # 相對路徑從根目錄開始
BOND_SERVICE_PORT = 8002

def start_service(directory, port):
    """在背景啟動一個 FastAPI 服務。"""
    print(f"正在從目錄 {directory} 啟動服務於埠號 {port}...")
    # 直接使用系統環境中的 uvicorn
    uvicorn_executable = "uvicorn"

    process = subprocess.Popen(
        [uvicorn_executable, "main:app", "--host", "0.0.0.0", "--port", str(port)],
        cwd=directory, # 在指定的目錄下執行
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    time.sleep(5) # 等待服務啟動
    print(f"服務應該已在 http://127.0.0.1:{port} 上運行。")
    return process

def get_console_logs():
    """從 browser-tools-server 獲取控制台日誌。"""
    try:
        response = httpx.get(f"{SERVER_URL}/console-logs")
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        print(f"請求日誌時出錯: {e}")
        return None

def main():
    """主測試流程。"""
    bond_service_process = None
    try:
        # 1. 啟動依賴的服務
        bond_service_process = start_service(BOND_SERVICE_DIR, BOND_SERVICE_PORT)

        # 2. 提示手動操作
        print("\n--- MCP/Browser Tools 驗證 POC ---")
        print("\n請執行以下手動步驟：")
        print("1. 確保 `browser-tools-server` 和 `browser-tools-mcp` 正在運行。")
        print("2. 打開一個 Chrome 瀏覽器分頁 (可能需要安裝 AgentDeskAI 的擴充功能)。")
        print(f"3. 導航到 http://127.0.0.1:{BOND_SERVICE_PORT}/chart/gdp")

        input("\n完成上述步驟後，請按 Enter 鍵繼續以抓取瀏覽器日誌...")

        # 3. 執行驗證
        print("\n正在從 Browser Tools Server 抓取控制台日誌...")
        logs = get_console_logs()

        if logs is None:
            print("\n測試失敗：無法從伺服器獲取日誌。")
            return

        print(f"\n成功獲取到 {len(logs)} 條日誌。")
        if logs:
            print("日誌內容:")
            print(json.dumps(logs, indent=2, ensure_ascii=False))

        has_errors = any(log.get('level') == 'error' for log in logs)

        if has_errors:
            print("\n[結論] 測試發現錯誤：控制台中存在錯誤級別的日誌。")
        else:
            print("\n[結論] 測試通過：控制台中沒有發現錯誤級別的日誌。")

    finally:
        # 4. 清理：確保服務被關閉
        if bond_service_process:
            print("\n正在關閉 bond_data_service...")
            bond_service_process.terminate()
            bond_service_process.wait()
            print("服務已關閉。")

if __name__ == "__main__":
    # 更改當前工作目錄到專案根目錄，以確保相對路徑正確
    # (這是一個假設，如果腳本不是從根目錄執行)
    # os.chdir('../') # 如果從 mcp_poc 執行，則需要回到上一層
    main()