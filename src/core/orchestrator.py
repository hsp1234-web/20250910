#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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

# --- 路徑修正 (必須在所有專案內部模組導入之前) ---
# 將 src 目錄新增到 Python 的搜尋路徑中
# 這樣可以確保無論從哪裡執行，都能正確找到 db, api 等模組
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = SRC_DIR.parent

# --- 現在可以安全地導入專案內部模組了 ---
from db.client import DBClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout # 將協調器的日誌輸出到 stdout
)
log = logging.getLogger('orchestrator')

# --- 全域變數 ---
processes = []
threads = []
stop_event = threading.Event()
db_client = None

# --- 公用函式 ---
def find_free_port():
    """找到一個可用的埠號。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def stream_reader(stream, prefix, ready_event=None, ready_signal=None, port_list=None, port_regex=None):
    """
    讀取子程序的輸出流，記錄日誌，並可選地設置就緒事件和提取埠號。
    """
    try:
        for line in iter(stream.readline, ''):
            if not line:
                break
            stripped_line = line.strip()
            log.info(f"[{prefix}] {stripped_line}")

            if ready_event and not ready_event.is_set() and ready_signal and ready_signal in stripped_line:
                ready_event.set()
                log.info(f"✅ 偵測到來自 '{prefix}' 的就緒信號 '{ready_signal}'！")

            if port_list is not None and port_regex:
                match = re.search(port_regex, stripped_line)
                if match:
                    port = int(match.group(1))
                    port_list.append(port)
                    log.info(f"✅ 偵測到來自 '{prefix}' 的埠號: {port}")
    except Exception as e:
        log.error(f"讀取流 '{prefix}' 時發生錯誤: {e}", exc_info=True)


def main():
    parser = argparse.ArgumentParser(description="系統協調器。")
    parser.add_argument("--mock", action="store_true", help="如果設置，則 worker 將以模擬模式運行。")
    parser.add_argument("--port", type=int, default=None, help="指定 API 伺服器運行的固定埠號。")
    args, _ = parser.parse_known_args()

    global db_client
    try:
        log.info("--- [協調器啟動] ---")

        # --- POC 優化：提前回報 URL ---
        # 1. 預先決定 API 埠號
        api_port = args.port if args.port else find_free_port()
        proxy_url = f"http://127.0.0.1:{api_port}"

        # 2. 立即向外部監聽器（如 colabPro.py）報告 URL
        # 這是整個優化流程的關鍵，它將 URL 的可用性與後端服務的完全就緒脫鉤。
        print(f"PROXY_URL: {proxy_url}", flush=True)
        log.info(f"已向外部監聽器提前報告代理 URL: {proxy_url}")
        # --- POC 優化結束 ---

        # 1. 啟動資料庫管理者 (已升級至 FastAPI/Uvicorn)
        log.info("🔧 正在啟動基於 Uvicorn 的資料庫管理器...")

        # 為 DB 管理器分配一個可用埠號
        db_manager_port = find_free_port()
        os.environ['DB_MANAGER_PORT'] = str(db_manager_port)
        log.info(f"已為資料庫管理器分配埠號: {db_manager_port}")

        # 使用 Uvicorn 啟動 FastAPI 應用
        db_manager_cmd = [
            sys.executable, "-m", "uvicorn",
            "src.db.manager:app",
            "--host", "127.0.0.1",
            "--port", str(db_manager_port),
            "--log-level", "info"
        ]

        # 建立一個包含正確 PYTHONPATH 的環境
        proc_env = os.environ.copy()
        python_path = proc_env.get("PYTHONPATH", "")
        proc_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + python_path

        # 設定就緒信號
        db_ready_event = threading.Event()
        # Uvicorn 應用啟動完成後會打印此訊息
        uvicorn_ready_signal = "Application startup complete"

        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=proc_env)
        processes.append(db_manager_proc)
        log.info(f"資料庫管理器程序已啟動，PID: {db_manager_proc.pid}")

        # 啟動一個執行緒來讀取輸出並監聽就緒信號
        db_stdout_thread = threading.Thread(
            target=stream_reader,
            args=(db_manager_proc.stdout, 'db_manager'),
            kwargs={'ready_event': db_ready_event, 'ready_signal': uvicorn_ready_signal}
        )
        db_stdout_thread.daemon = True
        threads.append(db_stdout_thread)
        db_stdout_thread.start()

        # 等待 Uvicorn 發出就緒信號
        log.info(f"等待資料庫管理器發出就緒信號 ('{uvicorn_ready_signal}')...")
        ready = db_ready_event.wait(timeout=30) # 30 秒超時
        if not ready:
            raise RuntimeError("等待資料庫管理器就緒超時。")

        # 檢查子程序是否意外終止
        if db_manager_proc.poll() is not None:
            raise RuntimeError(f"資料庫管理器程序在啟動期間意外終止，返回碼: {db_manager_proc.returncode}")

        log.info(f"✅ 資料庫管理器 API 已在埠號 {db_manager_port} 上就緒。")

        # 2. 初始化 DB 客戶端
        db_client = DBClient()
        log.info("✅ DB 客戶端初始化完成。")

        # 3. 啟動 API 伺服器
        log.info("🔧 正在啟動 API 伺服器...")
        # 此處的 api_port 已在函數開頭的 POC 優化區塊中定義
        api_server_cmd = [sys.executable, "-m", "api.api_server", "--port", str(api_port)]
        if args.mock:
            api_server_cmd.append("--mock")

        api_env = os.environ.copy()
        if args.mock:
            api_env["API_MODE"] = "mock"

        # 確保 API 伺服器子程序也能找到 src 目錄
        python_path = api_env.get("PYTHONPATH", "")
        api_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + python_path

        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=api_env)
        processes.append(api_proc)
        log.info(f"API 伺服器程序已啟動，PID: {api_proc.pid}，埠號: {api_port}")

        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server', None, None))
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr', None, None))
        threads.extend([api_stdout_thread, api_stderr_thread])
        for t in [api_stdout_thread, api_stderr_thread]:
            t.daemon = True
            t.start()

        log.info("🚫 [架構性決策] Worker 程序已被永久停用，以支援 WebSocket 驅動的新架構。")
        log.info("--- [協調器進入監控模式] ---")

        last_heartbeat_time = time.time()
        while not stop_event.is_set():
            # 1. 檢查所有子程序是否仍在運行
            for proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"子程序 {proc.args} (PID: {proc.pid}) 已意外終止，返回碼: {proc.returncode}")

            # 4. 心跳檢查
            if time.time() - last_heartbeat_time > 15:
                try:
                    active_tasks = db_client.are_tasks_active()
                    log.info(f"HEARTBEAT: RUNNING {'(TASKS ACTIVE)' if active_tasks else ''}")
                    last_heartbeat_time = time.time()
                except Exception as e:
                    log.error(f"心跳檢查失敗: {e}")
                    # 如果心跳連續失敗，可能需要採取行動
            time.sleep(2)

    except (Exception, KeyboardInterrupt) as e:
        if isinstance(e, KeyboardInterrupt):
            log.warning("捕獲到手動中斷信號 (KeyboardInterrupt)...")
        else:
            log.critical(f"協調器發生致命錯誤: {e}", exc_info=True)
    finally:
        log.info("--- [協調器開始關閉程序] ---")
        stop_event.set()
        for p in reversed(processes):
            try:
                if p.poll() is None:
                    log.info(f"正在終止程序: {p.args} (PID: {p.pid})")
                    p.terminate()
                    p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning(f"程序 {p.pid} 未能在5秒內終止，將強制終止。")
                p.kill()
            except Exception as kill_e:
                log.error(f"終止程序 {p.pid} 時發生錯誤: {kill_e}")

        log.info("等待所有日誌執行緒結束...")
        for t in threads:
            if t.is_alive():
                t.join(timeout=2)
        log.info("✅ 所有子程序與執行緒已清理完畢。協調器已關閉。")
        sys.exit(1 if 'e' in locals() and not isinstance(e, KeyboardInterrupt) else 0)

if __name__ == "__main__":
    main()
