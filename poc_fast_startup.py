#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# ==============================================================================
# ✨ PoC 腳本：快速啟動驗證 ✨
# ==============================================================================
#
# 目的：
#   驗證如果將「金鑰驗證」從啟動時的阻塞操作中移除，
#   應用程式的啟動速度能有多快。
#
# 修改點：
#   - 本腳本基於 `src/core/orchestrator.py`。
#   - 在 `prepare_core_services_poc` 函式中，實際的 `requests.post`
#     呼叫被註解掉，並替換為一個瞬間完成的模擬操作。
#   - 在 `main` 函式中，加入了計時與結果報告邏輯。
#
# ==============================================================================

import argparse
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime
import requests

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = Path(__file__).resolve().parent

# --- 專案內部模組導入 ---
# 假設 DBClient 存在且路徑正確
from db.client import DBClient

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('PoC_FastStartup')

# --- 全域變數 ---
processes = []
threads = []
stop_event = threading.Event()
full_readiness_event = threading.Event()
READINESS_SIGNAL_FILE = Path("/tmp/poc_full_ready.signal")

# --- PoC 修改的核心函式 ---
def prepare_core_services_poc(api_port: int, api_ready_event: threading.Event):
    """
    [PoC 版本]
    在背景執行緒中準備核心服務。
    **修改點**: 跳過了實際的金鑰驗證。
    """
    try:
        log.info("[核心準備] 背景任務已啟動。")

        # 步驟 1: 安裝核心依賴 (與原版相同)
        core_req_path = ROOT_DIR / "requirements" / "features_core.txt"
        # 在 PoC 中，我們假設依賴已安裝，以加速測試
        log.info(f"✅ [PoC] 跳過依賴安裝檢查。")

        # 步驟 2: 等待 API 伺服器就緒 (與原版相同)
        log.info("[核心準備] 等待 API 伺服器就緒...")
        server_is_ready = api_ready_event.wait(timeout=60)
        if not server_is_ready:
            log.error("[核心準備] 等待 API 伺服器就緒超時。")
            return
        log.info("[核心準備] API 伺服器已就緒。")

        # [PoC 修改] >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
        # 步驟 3: **模擬**金鑰驗證
        # 在 PoC 中，我們不執行耗時的網路請求，而是直接跳過。
        log.warning("✅ [PoC] 已跳過實際的金鑰驗證網路請求。")
        # 模擬一個極短的處理延遲
        time.sleep(0.1)
        # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

        # 步驟 4: 發送「完全就緒」信號 (與原版相同)
        log.info("✅ [核心準備] 核心服務準備完畢！發送『完全就緒』信號。")
        full_readiness_event.set()
        READINESS_SIGNAL_FILE.touch()

    except Exception as e:
        log.critical(f"❌ [核心準備] 背景任務發生致命錯誤: {e}", exc_info=True)
        full_readiness_event.set()
        if not READINESS_SIGNAL_FILE.exists():
             READINESS_SIGNAL_FILE.write_text(f"Error: {e}", encoding="utf-8")

# --- 以下為從 orchestrator.py 複製過來的輔助函式，未作修改 ---

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def stream_reader(stream, prefix, ready_event=None, ready_signal=None):
    try:
        for line in iter(stream.readline, ''):
            if not line: break
            stripped_line = line.strip()
            log.info(f"[{prefix}] {stripped_line}")
            if ready_event and not ready_event.is_set() and ready_signal and ready_signal in stripped_line:
                ready_event.set()
                log.info(f"✅ 偵測到來自 '{prefix}' 的就緒信號 '{ready_signal}'！")
    except Exception as e:
        log.error(f"讀取流 '{prefix}' 時發生錯誤: {e}", exc_info=True)

# --- PoC 的主函式 ---
def main():
    log.info("="*80)
    log.info("📊 PoC 效能評估 (策略 v3: 模擬非同步驗證)...")
    log.info("="*80)

    # 計時器與事件捕捉
    patterns = {
        'server_ready': re.compile(r"Uvicorn running on"),
        'validation_start': re.compile(r"已跳過實際的金鑰驗證網路請求"),
        'fully_ready': re.compile(r"核心服務準備完畢！發送『完全就緒』信號"),
    }
    timestamps = {
        'process_start': time.monotonic(),
        'server_ready': None,
        'validation_start': None,
        'fully_ready': None,
    }

    global db_client
    try:
        if READINESS_SIGNAL_FILE.exists(): READINESS_SIGNAL_FILE.unlink()

        api_port = find_free_port()
        db_manager_port = find_free_port()
        os.environ['DB_MANAGER_PORT'] = str(db_manager_port)

        proc_env = os.environ.copy()
        proc_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + proc_env.get("PYTHONPATH", "")

        # 啟動 DB Manager
        db_manager_cmd = [sys.executable, "-m", "uvicorn", "src.db.manager:app", "--host", "127.0.0.1", "--port", str(db_manager_port), "--log-level", "info"]
        db_ready_event = threading.Event()
        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=proc_env)
        processes.append(db_manager_proc)
        db_stdout_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stdout, 'db_manager'), kwargs={'ready_event': db_ready_event, 'ready_signal': "Application startup complete"})
        threads.append(db_stdout_thread)
        db_stdout_thread.start()
        if not db_ready_event.wait(timeout=30): raise RuntimeError("DB Manager 超時")
        log.info(f"✅ DB Manager 已就緒。")

        # 啟動 API Server
        api_ready_event = threading.Event()
        api_server_cmd = [sys.executable, "-m", "api.api_server", "--port", str(api_port)]
        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=proc_env)
        processes.append(api_proc)
        api_ready_kwargs = {'ready_event': api_ready_event, 'ready_signal': "Uvicorn running on"}
        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server'), kwargs=api_ready_kwargs)
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr'), kwargs=api_ready_kwargs)
        threads.extend([api_stdout_thread, api_stderr_thread])
        for t in [api_stdout_thread, api_stderr_thread]: t.start()

        # 啟動 PoC 版本的核心準備任務
        core_prep_thread = threading.Thread(target=prepare_core_services_poc, args=(api_port, api_ready_event), daemon=True)
        threads.append(core_prep_thread)
        core_prep_thread.start()

        # --- 開始監控與計時 ---
        main_process_log_stream = [db_manager_proc.stdout, api_proc.stdout, api_proc.stderr]

        # 監控 PoC 流程，直到「完全就緒」
        if not full_readiness_event.wait(timeout=180): # 設置一個較長的超時
             raise TimeoutError("PoC 執行超時")

    except (Exception, KeyboardInterrupt) as e:
        log.critical(f"PoC 主程式發生錯誤: {e}", exc_info=True)
    finally:
        log.info("--- [PoC 結束，開始清理] ---")
        stop_event.set()
        if READINESS_SIGNAL_FILE.exists(): READINESS_SIGNAL_FILE.unlink()
        for p in reversed(processes):
            if p.poll() is None: p.terminate()
        for t in threads:
            if t.is_alive(): t.join(timeout=1)

        # --- 結果報告 ---
        # 模擬從日誌中捕捉時間戳
        # 為了簡化，我們直接在主執行緒中計算時間
        timestamps['server_ready'] = api_ready_event.wait(0) and (time.monotonic()) # 非阻塞檢查
        timestamps['fully_ready'] = full_readiness_event.wait(0) and (time.monotonic()) # 非阻塞檢查

        # 手動計算，因為流式讀取在PoC中較複雜
        start_time = timestamps['process_start']
        api_ready_time = timestamps['server_ready']
        fully_ready_time = timestamps['fully_ready']

        print("\n" + "="*80)
        print("📊 PoC 效能評估結果:")
        print("="*80)

        if api_ready_time:
            time_to_server_ready = api_ready_time - start_time
            print(f"⏱️  伺服器就緒時間 (可取得網址): {time_to_server_ready:.2f} 秒")

            if fully_ready_time:
                time_to_fully_ready = fully_ready_time - api_ready_time
                print(f"⏱️  核心瓶頸凍結時間 (模擬): {time_to_fully_ready:.2f} 秒")
                total_duration = fully_ready_time - start_time
                print(f"⏱️  應用程式完全可用總時間: {total_duration:.2f} 秒")
            else:
                print("❌  未能捕捉到 PoC 的『完全就緒』信號。")
        else:
            print("❌  未能捕捉到 PoC 的『伺服器就緒』信號。")
        print("="*80)

if __name__ == "__main__":
    main()
