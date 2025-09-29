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
import json
from pathlib import Path
import requests # V5.5 新增導入

# --- 路徑修正 (必須在所有專案內部模組導入之前) ---
SRC_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC_DIR))
ROOT_DIR = SRC_DIR.parent

# --- 現在可以安全地導入專案內部模組了 ---
from db.client import DBClient

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

# --- V6.0 微服務架構變數 ---
SERVICE_REGISTRY_FILE = Path("/tmp/service_registry.json")

# --- V5.5 啟動優化: 新增全域就緒信號 ---
full_readiness_event = threading.Event()
READINESS_SIGNAL_FILE = Path("/tmp/full_ready.signal")


def find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def run_command(command, cwd=None, check=True, log_prefix=""):
    """執行一個命令並記錄其輸出。"""
    log.info(f"[{log_prefix}] 執行命令: {' '.join(str(c) for c in command)}")
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, encoding='utf-8',
            cwd=cwd, check=check, timeout=300 # 5分鐘超時以防萬一
        )
        # 即使成功，也記錄輸出以供除錯
        if result.stdout and result.stdout.strip():
            log.debug(f"[{log_prefix}] STDOUT:\n{result.stdout.strip()}")
        if result.stderr and result.stderr.strip():
            log.debug(f"[{log_prefix}] STDERR:\n{result.stderr.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        log.error(f"[{log_prefix}] 命令執行失敗！返回碼: {e.returncode}")
        log.error(f"[{log_prefix}] STDOUT: {e.stdout.strip() if e.stdout else 'N/A'}")
        log.error(f"[{log_prefix}] STDERR: {e.stderr.strip() if e.stderr else 'N/A'}")
        raise
    except subprocess.TimeoutExpired as e:
        log.error(f"[{log_prefix}] 命令執行超時！")
        raise

# --- V6.0 微服務啟動器 ---
def launch_microservice(service_path: Path, ready_signal="Uvicorn running on"):
    """
    為單個微服務建立環境、安裝依賴並啟動它。
    (JULES'S FIX 2025-09-29): 新增服務就緒等待和信號檔案機制。
    """
    service_name = service_path.name
    log_prefix = f"Service:{service_name}"
    log.info(f"--- 正在啟動微服務: {service_name} ---")

    venv_dir = service_path / ".venv"
    req_file = service_path / "requirements.txt"
    main_script = service_path / "main.py"
    python_exec = venv_dir / "bin" / "python"

    # 步驟 1: 建立虛擬環境
    if not venv_dir.exists():
        run_command(["uv", "venv", venv_dir, "--seed"], log_prefix=log_prefix)
    else:
        log.info(f"[{log_prefix}] 虛擬環境已存在，跳過建立。")

    # 步驟 2: 安裝依賴
    lock_file = venv_dir / ".install_lock"
    should_install = True
    if lock_file.exists() and req_file.exists():
        if lock_file.stat().st_mtime > req_file.stat().st_mtime:
            log.info(f"[{log_prefix}] 依賴未變更，跳過安裝。")
            should_install = False

    if should_install and req_file.exists():
        log.info(f"[{log_prefix}] 正在安裝或更新依賴...")
        run_command([
            "uv", "pip", "install", "-p", str(python_exec), "-r", str(req_file)
        ], log_prefix=log_prefix)
        lock_file.touch()
    elif not req_file.exists():
        log.warning(f"[{log_prefix}] 找不到 requirements.txt，跳過依賴安裝。")

    # 步驟 3: 啟動服務
    port = find_free_port()
    proc_env = os.environ.copy()
    proc_env["PORT"] = str(port)
    if "FRED_API_KEY" in os.environ:
        proc_env["FRED_API_KEY"] = os.environ["FRED_API_KEY"]
        log.info(f"[{log_prefix}] 已將 FRED_API_KEY 注入到服務環境中。")

    command = [
        str(python_exec), "-m", "uvicorn", f"{main_script.stem}:app",
        "--host", "127.0.0.1", "--port", str(port)
    ]
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding='utf-8', env=proc_env, cwd=service_path
    )

    # 步驟 4: 等待服務就緒
    ready_event = threading.Event()
    log_thread = threading.Thread(
        target=stream_reader,
        args=(process.stdout, log_prefix, ready_event, ready_signal),
        daemon=True
    )
    log_thread.start()
    threads.append(log_thread)

    if not ready_event.wait(timeout=60):
        process.kill()
        raise RuntimeError(f"服務 {service_name} 在 60 秒內啟動超時。")

    log.info(f"✅ 微服務 '{service_name}' 已在埠號 {port} 上就緒，進程 PID: {process.pid}")

    # 步驟 5: 為 key_master_service 建立信號檔案
    if service_name == "key_master_service":
        signal_file = Path(f"/tmp/{service_name}.ready")
        signal_file.touch()
        log.info(f"✅ 已為 '{service_name}' 建立就緒信號檔案: {signal_file}")

    return service_name, port, process

def start_all_microservices():
    """
    掃描 `services` 目錄並啟動所有找到的微服務。
    """
    services_dir = ROOT_DIR / "services"
    if not services_dir.is_dir():
        log.info("`services` 目錄不存在，跳過微服務啟動。")
        return

    service_paths = [d for d in services_dir.iterdir() if d.is_dir() and (d / "main.py").exists()]
    if not service_paths:
        log.info("在 `services` 目錄中未找到任何有效的微服務。")
        return

    log.info(f"偵測到 {len(service_paths)} 個微服務，準備啟動...")

    service_registry = {}
    # 順序啟動，也可以改為並行
    for service_path in service_paths:
        try:
            service_name, port, process = launch_microservice(service_path)
            service_registry[service_name] = {"port": port, "status": "running"}
            processes.append(process) # 將進程加入全域列表以便監控和清理
        except Exception as e:
            log.error(f"啟動服務 {service_path.name} 失敗: {e}", exc_info=True)
            service_registry[service_path.name] = {"port": None, "status": "failed"}

    # 將服務註冊資訊寫入檔案
    with open(SERVICE_REGISTRY_FILE, 'w', encoding='utf-8') as f:
        json.dump(service_registry, f, indent=2)
    log.info(f"✅ 服務註冊資訊已寫入: {SERVICE_REGISTRY_FILE}")


# --- V5.5 舊有邏輯 (待移除) ---
def prepare_core_services(api_port: int, api_ready_event: threading.Event):
    """
    V6.0 更新：此函式的依賴安裝部分已被移除。
    它現在只負責觸發舊有的金鑰驗證流程。
    """
    try:
        log.info("[核心準備] 背景任務已啟動。")

        # 步驟 1: 等待 API 伺服器就緒
        log.info("[核心準備] 等待 API 伺服器就緒...")
        if not api_ready_event.wait(timeout=60):
            log.error("[核心準備] 等待 API 伺服器就緒超時。")
            full_readiness_event.set()
            READINESS_SIGNAL_FILE.touch()
            return

        # 步驟 2: 立即發送「完全就緒」信號
        log.info("✅ [核心準備] 核心服務準備完畢！發送『完全就緒』信號。")
        full_readiness_event.set()
        READINESS_SIGNAL_FILE.touch()

        # JULES (2025-09-25): 在此處啟動非必要依賴的背景安裝
        log.info("[核心準備] 準備在背景安裝重量級依賴...")
        non_essential_install_thread = threading.Thread(target=install_non_essential_dependencies_background, daemon=True)
        non_essential_install_thread.start()
        threads.append(non_essential_install_thread)

        # 步驟 3: 背景觸發金鑰驗證 (舊流程)
        def _run_validation_in_background():
            log.info("[金鑰驗證-背景] 等待2秒後開始...")
            time.sleep(2)
            validation_url = f"http://127.0.0.1:{api_port}/api/keys/validate"
            log.info(f"[金鑰驗證-背景] 正在向 {validation_url} 發送 POST 請求...")
            try:
                requests.post(validation_url, timeout=180)
            except Exception as req_e:
                log.error(f"[金鑰驗證-背景] 發送驗證請求時發生錯誤: {req_e}")

        log.info("[核心準備] 準備在背景啟動金鑰驗證...")
        validation_thread = threading.Thread(target=_run_validation_in_background, daemon=True)
        validation_thread.start()
        threads.append(validation_thread)

    except Exception as e:
        log.critical(f"❌ [核心準備] 背景任務發生致命錯誤: {e}", exc_info=True)


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


def install_core_dependencies():
    """
    安裝核心應用程式所需的所有 Python 依賴。
    會讀取 requirements/ 目錄下的多個 txt 檔案。
    """
    log.info("--- 正在安裝核心依賴 ---")
    requirements_dir = ROOT_DIR / "requirements"

    # JULES (2025-09-25): 優化。此處只安裝啟動時必需的同步依賴。
    # 重量級依賴 (如 analysis.txt) 將在後台線程中安裝。
    core_req_files = [
        "core.txt",
        "transcriber.txt",
        "downloader.txt",
        "gemini.txt",
    ]

    # 效能優化：新增一個簡單的 lock 機制，避免每次啟動都重新安裝
    lock_file = requirements_dir / ".install_lock"
    should_install = True

    if lock_file.exists():
        # 檢查 requirements/ 目錄下是否有任何 .txt 檔案比 lock 檔案新
        try:
            latest_req_time = max(f.stat().st_mtime for f in requirements_dir.glob("*.txt") if f.is_file())
            if lock_file.stat().st_mtime >= latest_req_time:
                log.info("核心依賴未變更，跳過安裝。")
                should_install = False
        except ValueError:
            # 如果 requirements/ 目錄下沒有任何 .txt 檔案，也無需安裝
            should_install = False

    if should_install:
        for req_file_name in core_req_files:
            req_file_path = requirements_dir / req_file_name
            if req_file_path.exists():
                log.info(f"正在從 {req_file_name} 安裝依賴...")
                try:
                    # 使用 uv 來快速安裝
                    run_command([
                        "uv", "pip", "install", "--system", "-r", str(req_file_path)
                    ], log_prefix="CoreDeps")
                except Exception as e:
                    log.error(f"從 {req_file_name} 安裝依賴時失敗: {e}")
                    raise RuntimeError(f"核心依賴安裝失敗: {req_file_name}")
            else:
                log.warning(f"找不到依賴文件 {req_file_path}，跳過。")

        # 成功安裝後，建立或更新 lock 檔案
        lock_file.touch()
        log.info("✅ 核心依賴安裝完成。")
    else:
        log.info("✅ 核心依賴已是最新狀態。")


def install_non_essential_dependencies_background():
    """
    [背景執行] 安裝非必要的重量級依賴，例如分析和報告工具。
    此函式應在一個獨立的執行緒中運行，以免阻塞主啟動流程。
    """
    log.info("--- [背景安裝] 開始安裝重量級依賴 ---")
    requirements_dir = ROOT_DIR / "requirements"
    non_essential_reqs = [
        "analysis.txt",
        "document_processing.txt"
    ]

    # 為避免與同步安裝或網路I/O衝突，稍作延遲
    time.sleep(5)

    for req_file_name in non_essential_reqs:
        req_file_path = requirements_dir / req_file_name
        if req_file_path.exists():
            log.info(f"[背景安裝] 正在從 {req_file_name} 安裝依賴...")
            try:
                # 使用 uv 來快速安裝
                run_command([
                    "uv", "pip", "install", "--system", "-r", str(req_file_path)
                ], log_prefix="NonEssentialDeps")
            except Exception as e:
                # 在背景執行緒中，我們只記錄錯誤，不讓它崩潰主程式
                log.error(f"[背景安裝] 從 {req_file_name} 安裝依賴時失敗: {e}")
        else:
            log.warning(f"[背景安裝] 找不到依賴文件 {req_file_path}，跳過。")

    log.info("--- [背景安裝] 重量級依賴安裝流程結束 ---")


def main():
    parser = argparse.ArgumentParser(description="系統協調器。")
    parser.add_argument("--mock", action="store_true", help="如果設置，則 worker 將以模擬模式運行。")
    parser.add_argument("--port", type=int, default=None, help="指定 API 伺服器運行的固定埠號。")
    args, _ = parser.parse_known_args()

    global db_client
    try:
        log.info("--- [協調器啟動 V6.0] ---")

        # 清理舊的信號和註冊檔案
        for f in [READINESS_SIGNAL_FILE, SERVICE_REGISTRY_FILE]:
            if f.exists():
                f.unlink()
                log.info(f"已清理舊的檔案: {f}")

        # V6.1 新增：安裝核心依賴
        install_core_dependencies()

        # 步驟 1: 啟動核心後端服務 (DB Manager, API Server)
        api_port = args.port if args.port else find_free_port()
        proxy_url = f"http://127.0.0.1:{api_port}"
        print(f"PROXY_URL: {proxy_url}", flush=True)

        log.info("🔧 正在啟動資料庫管理器...")
        db_manager_port = find_free_port()
        os.environ['DB_MANAGER_PORT'] = str(db_manager_port)
        db_manager_cmd = [sys.executable, "-m", "uvicorn", "src.db.manager:app", "--host", "127.0.0.1", "--port", str(db_manager_port), "--log-level", "info"]
        proc_env = os.environ.copy()
        proc_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + proc_env.get("PYTHONPATH", "")

        db_ready_event = threading.Event()
        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=proc_env)
        processes.append(db_manager_proc)
        db_stdout_thread = threading.Thread(target=stream_reader, args=(db_manager_proc.stdout, 'db_manager', db_ready_event, "Application startup complete"))
        db_stdout_thread.daemon = True
        threads.append(db_stdout_thread)
        db_stdout_thread.start()

        if not db_ready_event.wait(timeout=30): raise RuntimeError("等待資料庫管理器就緒超時。")
        log.info(f"✅ 資料庫管理器 API 已在埠號 {db_manager_port} 上就緒。")

        db_client = DBClient()
        log.info("✅ DB 客戶端初始化完成。")

        log.info("🔧 正在啟動主 API 伺服器...")
        api_ready_event = threading.Event()
        api_server_cmd = [sys.executable, "-m", "api.api_server", "--port", str(api_port)]
        if args.mock: api_server_cmd.append("--mock")

        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=proc_env)
        processes.append(api_proc)
        api_stdout_thread = threading.Thread(target=stream_reader, args=(api_proc.stdout, 'api_server', api_ready_event, "Uvicorn running on"))
        api_stderr_thread = threading.Thread(target=stream_reader, args=(api_proc.stderr, 'api_server_stderr', api_ready_event, "Uvicorn running on"))
        threads.extend([api_stdout_thread, api_stderr_thread])
        api_stdout_thread.daemon = True
        api_stderr_thread.daemon = True
        api_stdout_thread.start()
        api_stderr_thread.start()

        # 步驟 2: 啟動所有微服務
        start_all_microservices()

        # 步驟 3: 執行舊的核心準備任務 (發送就緒信號等)
        log.info("🚀 正在啟動核心服務準備任務 (背景執行)...")
        core_prep_thread = threading.Thread(target=prepare_core_services, args=(api_port, api_ready_event), daemon=True)
        threads.append(core_prep_thread)
        core_prep_thread.start()

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
        for f in [READINESS_SIGNAL_FILE, SERVICE_REGISTRY_FILE]:
            if f.exists():
                f.unlink()
        for p in reversed(processes):
            try:
                if p.poll() is None:
                    log.info(f"正在終止程序: {p.args} (PID: {p.pid})")
                    p.terminate()
                    p.wait(timeout=5)
            except subprocess.TimeoutExpired:
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
