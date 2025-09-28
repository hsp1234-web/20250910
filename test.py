import subprocess
import time
import os
import signal
import threading
import sys

# --- 設定 ---
ORCHESTRATOR_SCRIPT = os.path.join("src", "core", "orchestrator.py")
TIMEOUT_SECONDS = 120
SUCCESS_SIGNAL_FILE = "/tmp/full_ready.signal"
PYTHON_EXECUTABLE = sys.executable

# --- 顏色代碼 ---
class Color:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'

def print_color(message, color):
    """用指定的顏色打印訊息。"""
    print(f"{color}{message}{Color.END}")

def main():
    """測試腳本的主執行函式。"""
    # --- 緊急修復：手動安裝協調器自身啟動所需的關鍵依賴 ---
    try:
        essential_deps = ["requests", "httpx"]
        print_color(f"[測試儀] 正在強制安裝協調器啟動依賴: {essential_deps}...", Color.YELLOW)
        subprocess.run([PYTHON_EXECUTABLE, "-m", "pip", "install", *essential_deps], check=True, capture_output=True)
        print_color("[測試儀] 關鍵依賴安裝成功。", Color.GREEN)
    except subprocess.CalledProcessError as e:
        print_color(f"[測試失敗] 安裝關鍵依賴失敗: {e.stderr.decode()}", Color.RED)
        sys.exit(1)

    orchestrator_process = None
    timer = None

    def timeout_handler():
        """超時處理函式，在超時後會被呼叫。"""
        print_color(f"\n[測試失敗] {TIMEOUT_SECONDS} 秒超時！未能偵測到成功信號。", Color.RED)
        if orchestrator_process:
            print_color("[測試儀] 正在終止後端協調器...", Color.YELLOW)
            # 使用 os.killpg 來終止整個進程組，確保所有子服務都被關閉
            try:
                os.killpg(os.getpgid(orchestrator_process.pid), signal.SIGTERM)
            except ProcessLookupError:
                print_color("[測試儀] 協調器進程已不存在。", Color.YELLOW)
        # 以非零狀態碼退出，表示測試失敗
        sys.exit(1)

    print_color("="*50, Color.GREEN)
    print_color("=== 後端核心服務啟動測試 ===", Color.GREEN)
    print_color("="*50, Color.GREEN)
    print(f"測試目標: {ORCHESTRATOR_SCRIPT}")
    print(f"成功信號: {SUCCESS_SIGNAL_FILE}")
    print(f"超時設定: {TIMEOUT_SECONDS} 秒\n")

    # 在啟動前，先清理舊的成功信號檔案
    if os.path.exists(SUCCESS_SIGNAL_FILE):
        os.remove(SUCCESS_SIGNAL_FILE)
        print_color("[準備] 已清理舊的成功信號檔案。", Color.YELLOW)

    try:
        # 啟動倒數計時器
        timer = threading.Timer(TIMEOUT_SECONDS, timeout_handler)
        timer.start()
        print_color(f"[測試儀] {TIMEOUT_SECONDS} 秒倒數計時器已啟動。", Color.YELLOW)

        # 使用 subprocess.Popen 啟動後端協調器
        # preexec_fn=os.setsid 讓協調器及其所有子進程在一個新的進程組中運行，
        # 這使得我們可以在超時後乾淨地終止所有相關服務。
        print_color("[測試儀] 正在啟動後端協調器...", Color.YELLOW)
        orchestrator_process = subprocess.Popen(
            [PYTHON_EXECUTABLE, "-u", ORCHESTRATOR_SCRIPT],
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            preexec_fn=os.setsid
        )

        # 開始輪詢成功信號檔案
        print_color("[測試儀] 正在輪詢成功信號...", Color.YELLOW)
        start_time = time.time()
        while time.time() - start_time < TIMEOUT_SECONDS:
            # 檢查協調器是否意外終止
            if orchestrator_process.poll() is not None:
                print_color(f"\n[測試失敗] 後端協調器意外終止，返回碼: {orchestrator_process.returncode}", Color.RED)
                timer.cancel()
                sys.exit(1)

            # 檢查是否已成功
            if os.path.exists(SUCCESS_SIGNAL_FILE):
                elapsed_time = time.time() - start_time
                print_color(f"\n[測試成功] 在 {elapsed_time:.2f} 秒內偵測到成功信號！", Color.GREEN)
                timer.cancel() # 取消超時倒數
                break

            time.sleep(1) # 每秒檢查一次
        else:
            # 這段程式碼理論上不會被執行，因為超時會由 timer 處理，
            # 但作為一個備用的防護措施存在。
            timeout_handler()

    except FileNotFoundError:
        print_color(f"[測試失敗] 找不到啟動腳本: {ORCHESTRATOR_SCRIPT}", Color.RED)
        if timer:
            timer.cancel()
        sys.exit(1)
    except Exception as e:
        print_color(f"\n[測試失敗] 執行過程中發生未預期的錯誤: {e}", Color.RED)
        if timer:
            timer.cancel()
        sys.exit(1)
    finally:
        # 確保無論測試成功或失敗，所有進程都會被清理
        if orchestrator_process and orchestrator_process.poll() is None:
            print_color("\n[測試儀] 測試結束，正在清理後端服務...", Color.YELLOW)
            try:
                os.killpg(os.getpgid(orchestrator_process.pid), signal.SIGTERM)
                print_color("[測試儀] 所有後端服務已成功終止。", Color.YELLOW)
            except ProcessLookupError:
                 print_color("[測試儀] 協調器進程已不存在。", Color.YELLOW)


if __name__ == "__main__":
    main()