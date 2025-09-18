# src/core/managers/process_manager.py
import logging
import os
import re
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger('process_manager')

# --- 路徑設定 ---
# 專案根目錄 (wolf_project)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
# 原始碼目錄 (wolf_project/src)
SRC_DIR = ROOT_DIR / "src"

class ProcessManager:
    """負責啟動、監控和關閉所有應用子進程的管理器。"""

    def __init__(self):
        self.processes = []
        self.threads = []
        self.stop_event = threading.Event()
        self.db_ready_event = threading.Event()
        self.api_ready_event = threading.Event()
        self.api_port = None
        self.db_manager_port = None

    def _stream_reader(self, stream, prefix, ready_event=None, ready_signal=None):
        """讀取子進程的輸出流並記錄。"""
        try:
            for line in iter(stream.readline, ''):
                if not line or self.stop_event.is_set():
                    break
                stripped_line = line.strip()
                log.info(f"[{prefix}] {stripped_line}")

                if ready_event and not ready_event.is_set() and ready_signal and ready_signal in stripped_line:
                    ready_event.set()
                    log.info(f"✅ 偵測到來自 '{prefix}' 的就緒信號 '{ready_signal}'！")
        except Exception as e:
            if not self.stop_event.is_set():
                log.error(f"讀取流 '{prefix}' 時發生錯誤: {e}", exc_info=True)

    def _find_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def start_services(self, mock_mode=False):
        """啟動所有核心服務，如資料庫管理器和 API 伺服器。"""
        log.info("--- 開始啟動核心服務進程 ---")

        # --- 啟動資料庫管理器 ---
        log.info("🔧 正在啟動資料庫管理器...")
        self.db_manager_port = self._find_free_port()
        os.environ['DB_MANAGER_PORT'] = str(self.db_manager_port)
        db_manager_cmd = [sys.executable, "-m", "uvicorn", "src.db.manager:app", "--host", "127.0.0.1", "--port", str(self.db_manager_port), "--log-level", "info"]
        proc_env = os.environ.copy()
        python_path = proc_env.get("PYTHONPATH", "")
        proc_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + python_path

        db_manager_proc = subprocess.Popen(db_manager_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', env=proc_env)
        self.processes.append(db_manager_proc)

        db_stdout_thread = threading.Thread(target=self._stream_reader, args=(db_manager_proc.stdout, 'db_manager'), kwargs={'ready_event': self.db_ready_event, 'ready_signal': "Application startup complete"})
        db_stdout_thread.daemon = True
        self.threads.append(db_stdout_thread)
        db_stdout_thread.start()

        log.info("等待資料庫管理器就緒...")
        if not self.db_ready_event.wait(timeout=30):
            raise RuntimeError("等待資料庫管理器就緒超時。")
        log.info(f"✅ 資料庫管理器 API 已在埠號 {self.db_manager_port} 上就緒。")

        # --- 啟動 API 伺服器 ---
        log.info("🔧 正在啟動 API 伺服器...")
        self.api_port = self._find_free_port()
        api_server_cmd = [sys.executable, "-m", "api.api_server", "--port", str(self.api_port)]
        if mock_mode:
            api_server_cmd.append("--mock")

        api_env = os.environ.copy()
        if mock_mode:
            api_env["API_MODE"] = "mock"
        api_env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + api_env.get("PYTHONPATH", "")

        api_proc = subprocess.Popen(api_server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', env=api_env)
        self.processes.append(api_proc)

        api_ready_kwargs = {'ready_event': self.api_ready_event, 'ready_signal': "Uvicorn running on"}
        api_stdout_thread = threading.Thread(target=self._stream_reader, args=(api_proc.stdout, 'api_server'), kwargs=api_ready_kwargs)
        api_stderr_thread = threading.Thread(target=self._stream_reader, args=(api_proc.stderr, 'api_server_stderr'), kwargs=api_ready_kwargs)

        for t in [api_stdout_thread, api_stderr_thread]:
            t.daemon = True
            self.threads.append(t)
            t.start()

        log.info("等待 API 伺服器就緒...")
        if not self.api_ready_event.wait(timeout=60):
            raise RuntimeError("等待 API 伺服器就緒超時。")
        log.info(f"✅ API 伺服器已在埠號 {self.api_port} 上就緒。")
        log.info("--- 所有核心服務進程已啟動 ---")

        return self.api_port, self.api_ready_event

    def monitor_processes(self):
        """監控所有子進程的健康狀態，直到收到停止信號。"""
        log.info("--- [進程管理器進入監控模式] ---")
        try:
            while not self.stop_event.is_set():
                for proc in self.processes:
                    if proc.poll() is not None:
                        raise RuntimeError(f"子程序 {proc.args} (PID: {proc.pid}) 已意外終止，返回碼: {proc.returncode}")
                time.sleep(2)
        except RuntimeError as e:
            log.critical(f"監控到子程序意外終止: {e}")
            self.stop_event.set() # 觸發關閉流程
            raise # 重新拋出例外，讓上層協調器知道

    def shutdown(self):
        """
        按照「優雅終止 -> 強制終止」的兩階段策略，關閉所有子進程。
        """
        if self.stop_event.is_set():
            return

        log.info("--- [進程管理器開始關閉程序] ---")
        self.stop_event.set()

        # 階段一：優雅終止 (SIGTERM)
        for p in reversed(self.processes):
            if p.poll() is None:
                log.info(f"正在向進程 {p.pid} 發送終止信號 (SIGTERM)...")
                try:
                    p.terminate()
                except ProcessLookupError:
                    log.warning(f"嘗試終止進程 {p.pid} 時，它已經不存在。")

        # 等待一段時間讓進程自行關閉
        shutdown_start_time = time.monotonic()
        all_terminated = False
        while time.monotonic() - shutdown_start_time < 5:
            if all(p.poll() is not None for p in self.processes):
                all_terminated = True
                break
            time.sleep(0.1)

        if all_terminated:
            log.info("所有子進程已優雅地終止。")
        else:
            # 階段二：強制終止 (SIGKILL)
            log.warning("部分進程未能在 5 秒內終止，將強制終止 (SIGKILL)...")
            for p in reversed(self.processes):
                if p.poll() is None:
                    log.warning(f"正在強制終止進程 {p.pid} (SIGKILL)...")
                    try:
                        p.kill()
                    except ProcessLookupError:
                         log.warning(f"嘗試強制終止進程 {p.pid} 時，它已經不存在。")

        log.info("等待所有日誌執行緒結束...")
        for t in self.threads:
            if t.is_alive():
                t.join(timeout=2)
        log.info("✅ 所有子程序與執行緒已清理完畢。")
