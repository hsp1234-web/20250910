#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import asyncio
import itertools
import json
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any, List

import requests

# --- 路徑修正 (必須在所有專案內部模組導入之前) ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = SRC_DIR.parent

# --- 現在可以安全地導入專案內部模組了 ---
from db.client import DBClient
from tools.gemini_manager import GeminiManager
from tools.gemini_processor import GeminiProcessor

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('orchestrator')

# --- 全域變數 ---
processes = []
threads = []
stop_event = threading.Event()
db_client = None
gemini_manager = None # 全域的 GeminiManager 實例

# --- 設定 ---
# 批次處理的相關設定
BATCH_PROCESSING_INTERVAL_SECONDS = 60  # 每隔 60 秒執行一次批次處理
MAX_CONCURRENT_TASKS = 5  # 同時執行的最大非同步任務數量
GEMINI_API_TIMEOUT = 180 # API 請求的超時時間
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest" # 要使用的模型名稱
# 從 prompts/default_prompts.json 讀取模板 (簡易版)
# 在真實應用中，這應該由一個更健壯的設定管理器來處理
try:
    PROMPT_FILE = SRC_DIR / "prompts" / "default_prompts.json"
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        ANALYSIS_PROMPT_TEMPLATE = json.load(f).get("analyze_financial_report", "請分析以下內容：\n{content}")
except Exception as e:
    log.error(f"無法載入提示詞模板: {e}")
    ANALYSIS_PROMPT_TEMPLATE = "請分析以下內容：\n{content}"


# --- V5.5 啟動優化: 新增全域就緒信號 ---
full_readiness_event = threading.Event()
READINESS_SIGNAL_FILE = Path("/tmp/full_ready.signal")

# --- V5.5 啟動優化: 從 colabPro.py 移入的依賴安裝邏輯 ---
def _install_dependencies(req_files: list[Path], log_prefix=""):
    """
    智慧地檢查並只安裝缺失的依賴。
    這是從 colabPro.py 的 ServerManager 移植過來的核心邏輯。
    """
    log.info(f"[{log_prefix}] 開始檢查與安裝依賴...")
    install_start_time = time.monotonic()

    # ROOT_DIR 是在檔案頂部定義的專案根目錄
    checker_script = ROOT_DIR / "scripts" / "check_deps.py"
    if not checker_script.is_file():
        log.critical(f"[{log_prefix}] 依賴檢查腳本 'check_deps.py' 不存在！")
        raise FileNotFoundError("Dependency checker script not found.")

    req_file_paths = [str(p.resolve()) for p in req_files if p.is_file()]
    if not req_file_paths:
        log.info(f"[{log_prefix}] 找不到任何有效的依賴檔案。")
        return

    try:
        check_command = [sys.executable, str(checker_script.resolve())] + req_file_paths
        result = subprocess.run(check_command, capture_output=True, text=True, encoding='utf-8')

        # 如果檢查腳本出錯，為保險起見，假設所有套件都需要安裝
        missing_packages = result.stdout.strip().splitlines() if result.returncode == 0 and result.stdout.strip() else []
        if result.returncode != 0:
            log.warning(f"[{log_prefix}] 依賴檢查腳本執行失敗，將嘗試安裝所有套件。Stderr: {result.stderr}")
            # 從檔案中讀取所有套件
            all_packages = []
            for p in req_files:
                all_packages.extend(p.read_text(encoding='utf-8').strip().splitlines())
            missing_packages = [line for line in all_packages if line and not line.startswith("#")]


        if not missing_packages:
            log.info(f"✅ [{log_prefix}] 所有依賴均已滿足，無需安裝。")
            return

        log.info(f"[{log_prefix}] 偵測到 {len(missing_packages)} 個缺失的套件，開始安裝...")

        # 使用 pip 進行安裝
        pip_command = [sys.executable, "-m", "pip", "install"] + missing_packages
        log.info(f"[{log_prefix}] 使用 'pip' 進行安裝。")

        result = subprocess.run(pip_command, capture_output=True, text=True, encoding='utf-8')

        if result.stdout and result.stdout.strip():
            log.debug(f"[{log_prefix}] pip stdout:\n{result.stdout}")

        if result.returncode != 0:
            error_log = f"pip install 失敗！返回碼: {result.returncode}\n"
            if result.stderr and result.stderr.strip():
                error_log += f"STDERR:\n{result.stderr}\n"
            log.error(error_log)
            raise subprocess.CalledProcessError(result.returncode, pip_command, output=result.stdout, stderr=result.stderr)

        log.info(f"✅ [{log_prefix}] 依賴安裝完成。 (耗時: {time.monotonic() - install_start_time:.2f} 秒)")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        log.critical(f"[{log_prefix}] 依賴安裝失敗！ {e}")
        raise

# --- V5.5 啟動優化: 新增核心服務準備任務 ---
def prepare_core_services(api_port: int, api_ready_event: threading.Event):
    """
    在背景執行緒中準備所有核心服務。
    1. 安裝核心依賴。
    2. 觸發金鑰驗證。
    3. 發送完全就緒信號。
    """
    try:
        log.info("[核心準備] 背景任務已啟動。")

        # 步驟 1: 安裝核心依賴
        core_req_path = ROOT_DIR / "requirements" / "features_core.txt"
        _install_dependencies([core_req_path], log_prefix="核心服務")

        # 步驟 2: 等待 API 伺服器就緒
        log.info("[核心準備] 等待 API 伺服器就緒...")
        server_is_ready = api_ready_event.wait(timeout=60)

        if not server_is_ready:
            log.error("[核心準備] 等待 API 伺服器就緒超時，無法觸發金鑰驗證。")
            return

        log.info("[核心準備] API 伺服器已就緒，準備觸發金鑰驗證。")

        # 步驟 3: 觸發金鑰驗證
        validation_url = f"http://127.0.0.1:{api_port}/api/keys/validate"
        log.info(f"[核心準備] 正在向 {validation_url} 發送 POST 請求...")
        try:
            response = requests.post(validation_url, timeout=180)
            log.info(f"[核心準備] 金鑰驗證請求完成，狀態碼: {response.status_code}")
            if response.status_code != 200:
                log.warning(f"[核心準備] 金鑰驗證伺服器回應: {response.text[:200]}")
        except Exception as req_e:
            log.error(f"[核心準備] 發送驗證請求時發生網路層錯誤: {req_e}")
            # 即使驗證失敗，我們也應該繼續並設置就緒信號，因為核心依賴已安裝
            # UI 可以處理金鑰無效的情況

        # 步驟 4: 發送「完全就緒」信號
        log.info("✅ [核心準備] 核心服務準備完畢！發送『完全就緒』信號。")
        full_readiness_event.set()
        # 建立檔案信號供 api_server 檢查
        READINESS_SIGNAL_FILE.touch()

    except Exception as e:
        log.critical(f"❌ [核心準備] 背景任務發生致命錯誤: {e}", exc_info=True)
        # 即使失敗，也發出信號，讓前端知道發生了問題，而不是無限期等待
        full_readiness_event.set()
        if not READINESS_SIGNAL_FILE.exists():
             READINESS_SIGNAL_FILE.write_text(f"Error: {e}", encoding="utf-8")


# --- 非同步批次處理核心邏輯 ---

async def worker(file_to_process: Dict[str, Any], api_key, semaphore: asyncio.Semaphore) -> Dict[str, Any]:
    """
    單一檔案的非同步處理單元。

    Args:
        file_to_process (Dict): 從資料庫獲取的檔案記錄。
        api_key: 用於此次處理的 ApiKey 物件。
        semaphore: 用於控制併發的信號量。

    Returns:
        一個包含處理結果的字典。
    """
    file_id = file_to_process.get('id')
    file_path = file_to_process.get('file_path')
    log.info(f"[Worker] 開始處理檔案 ID: {file_id}，使用金鑰: {api_key.name}")

    async with semaphore:
        log.info(f"[Worker] 取得信號量，正在處理檔案 ID: {file_id}")
        try:
            # 讀取檔案內容
            # 注意：在真實的分散式系統中，檔案路徑可能需要轉換或從遠端儲存讀取
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            processor = GeminiProcessor(
                api_key=api_key.key,
                model_name=GEMINI_MODEL_NAME,
                timeout=GEMINI_API_TIMEOUT
            )

            analysis_result, error = await processor.analyze_content(content, ANALYSIS_PROMPT_TEMPLATE)

            if error:
                log.error(f"檔案 ID {file_id} 分析失敗: {error}")
                return {"file_id": file_id, "status": "failed", "error_message": error}
            else:
                log.info(f"檔案 ID {file_id} 分析成功。")
                # 將分析結果（JSON）轉換為字串存儲
                return {"file_id": file_id, "status": "processed", "analysis_result": json.dumps(analysis_result, ensure_ascii=False)}

        except Exception as e:
            log.error(f"處理檔案 ID {file_id} 時發生未預期的 Worker 錯誤: {e}", exc_info=True)
            return {"file_id": file_id, "status": "failed", "error_message": str(e)}

async def process_batch_async():
    """
    非同步批次處理的主函式。
    """
    log.info("--- [非同步批次處理] 開始執行 ---")

    if not db_client or not gemini_manager:
        log.warning("[非同步批次處理] DB 客戶端或 Gemini 管理器未初始化，跳過此次執行。")
        return

    # 1. 收集任務
    pending_files = db_client.get_files_by_status('pending')
    if not pending_files:
        log.info("[非同步批次處理] 沒有待處理的檔案，任務結束。")
        return

    log.info(f"[非同步批次處理] 發現 {len(pending_files)} 個待處理的檔案。")

    # 2. 準備資源
    all_keys = gemini_manager.get_all_keys()
    if not all_keys:
        log.error("[非同步批次處理] 金鑰池為空，無法處理檔案。")
        return

    key_cycle = itertools.cycle(all_keys)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)

    # 3. 建立受控的非同步任務
    tasks = []
    for file_record in pending_files:
        api_key = next(key_cycle)
        task = asyncio.create_task(worker(file_record, api_key, semaphore))
        tasks.append(task)

    # 4. 一次性併發派發並等待結果
    log.info(f"準備派發 {len(tasks)} 個非同步任務，最大併發數: {MAX_CONCURRENT_TASKS}...")
    results = await asyncio.gather(*tasks, return_exceptions=True)
    log.info("所有非同步任務執行完畢。")

    # 5. 批次更新狀態
    success_count = 0
    failure_count = 0
    for result in results:
        if isinstance(result, Exception):
            log.error(f"一個 Worker 任務因未捕捉的例外而失敗: {result}", exc_info=result)
            failure_count += 1
            continue

        file_id = result.get('file_id')
        status = result.get('status')

        if status == 'processed':
            db_client.update_file_status(
                file_id,
                'processed',
                analysis_result=result.get('analysis_result')
            )
            success_count += 1
        else:
            db_client.update_file_status(
                file_id,
                'failed',
                error_message=result.get('error_message')
            )
            failure_count += 1

    log.info(f"--- [非同步批次處理] 執行完畢 ---")
    log.info(f"成功: {success_count}，失敗: {failure_count}。")


def run_batch_processing_periodically():
    """
    在一個專門的執行緒中，定期執行非同步批次處理。
    """
    log.info("[批次處理執行緒] 已啟動，將每隔 {} 秒執行一次。".format(BATCH_PROCESSING_INTERVAL_SECONDS))
    while not stop_event.is_set():
        try:
            # 使用 asyncio.run 來執行頂層的 async 函式
            asyncio.run(process_batch_async())
        except Exception as e:
            log.error(f"[批次處理執行緒] 執行非同步任務時發生錯誤: {e}", exc_info=True)

        # 等待下一個週期或直到停止事件被觸發
        stop_event.wait(BATCH_PROCESSING_INTERVAL_SECONDS)
    log.info("[批次處理執行緒] 已停止。")


# --- 現有的服務管理邏輯 (保持不變) ---

def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def stream_reader(stream, prefix, ready_event=None, ready_signal=None, port_list=None, port_regex=None):
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

    global db_client, gemini_manager
    try:
        log.info("--- [協調器啟動 V5.5 + 非同步批次處理] ---")

        # 清理上一次執行的信號檔案
        if READINESS_SIGNAL_FILE.exists():
            READINESS_SIGNAL_FILE.unlink()
            log.info("已清理舊的就緒信號檔案。")

        api_port = args.port if args.port else find_free_port()
        proxy_url = f"http://127.0.0.1:{api_port}"
        print(f"PROXY_URL: {proxy_url}", flush=True)
        log.info(f"已向外部監聽器提前報告代理 URL: {proxy_url}")

        log.info("🔧 正在啟動基於 Uvicorn 的資料庫管理器...")
        db_manager_port = find_free_port()
        os.environ['DB_MANAGER_PORT'] = str(db_manager_port)
        db_manager_cmd = [sys.executable, "-m", "uvicorn", "src.db.manager:app", "--host", "127.0.0.1", "--port", str(db_manager_port), "--log-level", "info"]
        proc_env = os.environ.copy()
        python_path = proc_env.get("PYTHONPATH", "")
        proc_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + python_path

        db_ready_event = threading.Event()
        uvicorn_ready_signal = "Application startup complete"
        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=proc_env)
        processes.append(db_manager_proc)

        db_stdout_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stdout, 'db_manager'), kwargs={'ready_event': db_ready_event, 'ready_signal': uvicorn_ready_signal})
        db_stdout_thread.daemon = True
        threads.append(db_stdout_thread)
        db_stdout_thread.start()

        log.info(f"等待資料庫管理器發出就緒信號 ('{uvicorn_ready_signal}')...")
        if not db_ready_event.wait(timeout=30): raise RuntimeError("等待資料庫管理器就緒超時。")
        if db_manager_proc.poll() is not None: raise RuntimeError(f"資料庫管理器程序在啟動期間意外終止，返回碼: {db_manager_proc.returncode}")
        log.info(f"✅ 資料庫管理器 API 已在埠號 {db_manager_port} 上就緒。")

        db_client = DBClient()
        log.info("✅ DB 客戶端初始化完成。")

        # 初始化 Gemini Manager
        # 在真實應用中，金鑰應該從安全的設定檔或環境變數載入
        # 這裡我們假設金鑰儲存在環境變數 GOOGLE_API_KEYS_JSON 中
        # 格式: '[{"name": "key1", "value": "xxx"}, {"name": "key2", "value": "yyy"}]'
        api_keys_json = os.environ.get("GOOGLE_API_KEYS_JSON", "[]")
        try:
            api_keys = json.loads(api_keys_json)
            if not api_keys:
                log.warning("未提供任何 API 金鑰，非同步處理器將無法執行。")
            gemini_manager = GeminiManager(api_keys=api_keys)
        except (json.JSONDecodeError, ValueError) as e:
            log.error(f"無法載入或解析 API 金鑰: {e}")
            # 即使金鑰載入失敗，系統仍應繼續啟動
            gemini_manager = GeminiManager(api_keys=[])


        log.info("🔧 正在啟動 API 伺服器...")
        api_ready_event = threading.Event()
        api_server_cmd = [sys.executable, "-m", "api.api_server", "--port", str(api_port)]
        if args.mock: api_server_cmd.append("--mock")
        api_env = os.environ.copy()
        if args.mock: api_env["API_MODE"] = "mock"
        api_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + api_env.get("PYTHONPATH", "")

        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=api_env)
        processes.append(api_proc)

        api_ready_kwargs = {'ready_event': api_ready_event, 'ready_signal': "Uvicorn running on"}
        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server'), kwargs=api_ready_kwargs)
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr'), kwargs=api_ready_kwargs)
        threads.extend([api_stdout_thread, api_stderr_thread])
        for t in [api_stdout_thread, api_stderr_thread]:
            t.daemon = True
            t.start()

        log.info("🚀 正在啟動核心服務準備任務 (背景執行)...")
        core_prep_thread = threading.Thread(target=prepare_core_services, args=(api_port, api_ready_event), daemon=True)
        threads.append(core_prep_thread)
        core_prep_thread.start()

        # --- 啟動新的非同步批次處理執行緒 ---
        log.info("🚀 正在啟動非同步批次處理監控執行緒...")
        batch_thread = threading.Thread(target=run_batch_processing_periodically, daemon=True)
        threads.append(batch_thread)
        batch_thread.start()
        # --- --------------------------- ---

        log.info("--- [協調器進入監控模式] ---")
        while not stop_event.is_set():
            for proc in processes:
                if proc.poll() is not None:
                    raise RuntimeError(f"子程序 {proc.args} (PID: {proc.pid}) 已意外終止，返回碼: {proc.returncode}")
            time.sleep(2)

    except (Exception, KeyboardInterrupt) as e:
        if isinstance(e, KeyboardInterrupt):
            log.warning("捕獲到手動中斷信號 (KeyboardInterrupt)...")
        else:
            log.critical(f"協調器發生致命錯誤: {e}", exc_info=True)
    finally:
        log.info("--- [協調器開始關閉程序] ---")
        stop_event.set()
        # 清理信號檔案
        if READINESS_SIGNAL_FILE.exists():
            READINESS_SIGNAL_FILE.unlink()
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
