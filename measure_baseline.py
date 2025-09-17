import subprocess
import sys
import time
import re
import os
from datetime import datetime

def analyze_startup_logs():
    """
    直接執行核心協調器 (orchestrator.py) 來分析啟動效能，
    繞過 Colab 特有的啟動腳本。
    """
    print("="*80)
    print("📊 開始基準效能評估 (策略 v2: 直接執行核心協調器)...")
    print("="*80)

    # 定義要從日誌中捕捉的關鍵事件的正則表達式
    patterns = {
        'server_ready': re.compile(r"Uvicorn running on"),
        'validation_start': re.compile(r"核心準備.*api/keys/validate"),
        'fully_ready': re.compile(r"核心服務準備完畢！發送『完全就緒』信號"),
    }

    # 用來儲存每個事件發生的時間戳
    timestamps = {
        'process_start': time.monotonic(),
        'server_ready': None,
        'validation_start': None,
        'fully_ready': None,
    }

    process = None
    try:
        # 準備執行環境，確保 src 目錄在 PYTHONPATH 中
        env = os.environ.copy()
        src_path = os.path.abspath('src')
        env['PYTHONPATH'] = f"{src_path}{os.pathsep}{env.get('PYTHONPATH', '')}"

        # 執行核心協調器
        command = [sys.executable, "src/core/orchestrator.py"]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1,
            env=env
        )

        print(f"🚀 正在執行: {' '.join(command)}")
        print(f"🕒 開始時間: {datetime.now().isoformat()}")
        print("-" * 80)

        # 逐行讀取子程序的輸出
        for line in iter(process.stdout.readline, ''):
            print(line, end='')  # 即時顯示原始日誌

            # 檢查是否匹配任何關鍵事件
            for key, pattern in patterns.items():
                if timestamps[key] is None and pattern.search(line):
                    timestamps[key] = time.monotonic()
                    print(f"\n>>>> 📊 事件捕捉: '{key}' at {datetime.now().isoformat()} <<<<\n", flush=True)

            # 如果所有事件都已捕捉，可以提前終止監控
            if all(ts is not None for key, ts in timestamps.items() if key != 'process_start'):
                print(">>>> 📊 所有關鍵事件已捕捉，終止監控。 <<<<")
                process.terminate()
                break

        process.wait(timeout=10)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"\n❌ 執行出錯: {e}")
        return
    except Exception as e:
        print(f"\n❌ 發生未預期的錯誤: {e}")
        return
    finally:
        if process and process.poll() is None:
            print("清理子程序...")
            process.kill()

    print("\n" + "="*80)
    print("📊 基準效能評估結果:")
    print("="*80)

    start_time = timestamps['process_start']

    if timestamps['server_ready']:
        time_to_server_ready = timestamps['server_ready'] - start_time
        print(f"⏱️  伺服器就緒時間 (可取得網址): {time_to_server_ready:.2f} 秒")
    else:
        print("❌  伺服器就緒時間: 未能捕捉到事件。")

    if timestamps['validation_start'] and timestamps['fully_ready']:
        time_to_fully_ready = timestamps['fully_ready'] - timestamps['validation_start']
        print(f"⏱️  核心瓶頸凍結時間 (金鑰驗證): {time_to_fully_ready:.2f} 秒")

        total_duration = timestamps['fully_ready'] - start_time
        print(f"⏱️  應用程式完全可用總時間: {total_duration:.2f} 秒")
    else:
        print("❌  未能捕捉到完整的驗證流程事件。")

    print("="*80)

if __name__ == "__main__":
    analyze_startup_logs()
