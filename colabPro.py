# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                      ║
# ║   ✨🐺 善狼一鍵啟動器 (v78 精簡版) 🐺                           ✨🐺 ║
# ║                                                                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║                                                                      ║
# ║ - V78 更新日誌 (2025-12-01):                                         ║
# ║   - **重構**: 移除所有微服務，改為單體應用架構。                     ║
# ║   - **簡化**: 大幅簡化依賴安裝和啟動流程。                           ║
# ║   - **移除**: 刪除所有與 FRED、LINE、債券等無關功能。                ║
# ║                                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

#@title ✨🐺 善狼一鍵啟動器 (v78 精簡版)  🐺 { vertical-output: true, display-mode: "form" }
#@markdown ---
#@markdown ### **核心設定**
#@markdown > **請確認以下兩個核心設定。**
#@markdown ---
#@markdown **後端版本分支或標籤**
TARGET_BRANCH_OR_TAG = "98.6" #@param {type:"string"}
#@markdown **自動從 Colab Secrets 載入的金鑰數量 (0-20)**
#@markdown > 輸入 `2` 將載入 `GOOGLE_API_KEY`, `_1`, `_2` 共三組金鑰。
KEY_LOAD_COUNT_LIMIT = 2 #@param {type:"number"}
#@markdown **日誌顯示行數 (1-15)**
#@markdown > `1` 為單行緊湊模式，`2-15` 為多行模式。
LOG_SPLIT_LINES = 2 #@param {type:"number"}
#@markdown ---
#@markdown > **設定完成後，點擊「執行」按鈕。**
#@markdown ---

if not 1 <= LOG_SPLIT_LINES <= 15:
    print(f"⚠️ 警告：日誌顯示行數設定值 ({LOG_SPLIT_LINES}) 超出有效範圍 (1-15)。將自動使用預設值 2。")
    LOG_SPLIT_LINES = 2

# ==============================================================================
# SECTION A: 進階設定
# ==============================================================================
REPOSITORY_URL = "https://github.com/hsp1234-web/20250910.git"
PROJECT_FOLDER_NAME = "wolf_project"
FORCE_REPO_REFRESH = True
ENABLE_COLAB_PROXY = True
ENABLE_LOCALTUNNEL = True
ENABLE_CLOUDFLARE = True
UI_REFRESH_SECONDS = 0.5
LOG_DISPLAY_LINES = 5
TIMEZONE = "Asia/Taipei"
SERVER_READY_TIMEOUT = 150

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import subprocess
import platform
import urllib.request
try:
    import pytz
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pytz"])
    import pytz
import os
import shutil
from pathlib import Path
import time
from datetime import datetime
import threading
from collections import deque
import re
from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output

# ==============================================================================
# SECTION 1: 管理器類別定義
# ==============================================================================

class LogManager:
    def __init__(self, max_lines, timezone_str):
        self._log_deque = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self.timezone = pytz.timezone(timezone_str)

    def log(self, level: str, message: str, source: str = "SYSTEM"):
        with self._lock:
            log_entry = {"timestamp": datetime.now(self.timezone), "level": level.upper(), "message": str(message)}
            self._log_deque.append(log_entry)

    def get_display_logs(self) -> list:
        with self._lock:
            return list(self._log_deque)

ANSI_COLORS = {"SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m", "CRITICAL": "\033[31m", "RESET": "\033[0m"}
def colorize(text, level):
    return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager
        self._stats = stats_dict
        self._refresh_rate = refresh_rate
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["✨🐺 善狼一鍵啟動器 (v78 精簡版) 🐺", ""]
        for log in self._log_manager.get_display_logs():
            ts, level, msg = log['timestamp'].strftime('%H:%M:%S'), log['level'], log['message']
            if LOG_SPLIT_LINES == 1:
                output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {msg}")
            else:
                output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)}")
                num_msg_lines = max(1, LOG_SPLIT_LINES - 1)
                avg_len = len(msg) / num_msg_lines
                start_index = 0
                for i in range(num_msg_lines):
                    if start_index >= len(msg): break
                    end_index = len(msg) if i == num_msg_lines - 1 else int(start_index + avg_len + 0.5)
                    line = msg[start_index:end_index].strip()
                    if line: output_buffer.append(line)
                    start_index = end_index

        urls = self._stats.get('urls', {})
        if urls:
            output_buffer.append("\n🔗 公開存取網址:")
            for name, info in sorted(urls.items(), key=lambda item: item[1].get('priority', 99)):
                if info['status'] == 'ready':
                    line = f"  - {name}: {colorize(info['url'], 'SUCCESS')}"
                    if 'password' in info: line += f" (密碼: {info['password']})"
                    output_buffer.append(line)
                else:
                    output_buffer.append(f"  - {name}: 正在啟動中...")

        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError:
            cpu, ram = "N/A", "N/A"
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append(f"\n⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            clear_output(wait=True); print("\n".join(self._build_output_buffer()), flush=True); time.sleep(self._refresh_rate)

    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=2)

class ServerManager:
    def __init__(self, log_manager, stats_dict):
        self._log_manager = log_manager; self._stats = stats_dict
        self.server_process = None; self.server_ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = 8000 # 固定埠號

    def _inject_keys_background(self, project_path: Path):
        self._log_manager.log("INFO", "[背景] 開始執行金鑰注入...")
        try:
            key_injector_script = project_path / "scripts" / "colab_key_injector.py"
            if not key_injector_script.is_file():
                self._log_manager.log("WARN", f"未找到金鑰注入腳本，跳過。")
                return

            from google.colab import userdata
            self._log_manager.log("INFO", "正在從 Colab Secrets 獲取金鑰...")
            base_key_name = "GOOGLE_API_KEY"
            target_key_names = [base_key_name] + [f"{base_key_name}_{i}" for i in range(1, KEY_LOAD_COUNT_LIMIT + 1)]
            keys_to_inject = [userdata.get(name) for name in target_key_names if userdata.get(name)]

            if not keys_to_inject:
                 self._log_manager.log("WARN", "未獲取到任何金鑰，跳過注入。")
                 return

            command = [sys.executable, str(key_injector_script.resolve()), "--mode", "manual", "--manual-keys", "\n".join(keys_to_inject)]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            for line in iter(process.stdout.readline, ''): self._log_manager.log("INFO", f"[金鑰注入] {line.strip()}")
            process.wait()
            self._log_manager.log("SUCCESS", f"✅ 金鑰注入完成，返回碼: {process.returncode}。")
        except Exception as e: self._log_manager.log("ERROR", f"金鑰注入時發生錯誤: {e}")

    def _run(self):
        try:
            self._log_manager.log("BATTLE", "=== 啟動器核心流程開始 ===")
            self._stats['status'] = "🚀 準備執行環境..."
            project_path = Path(PROJECT_FOLDER_NAME)
            if FORCE_REPO_REFRESH and project_path.exists(): shutil.rmtree(project_path)
            self._log_manager.log("INFO", f"正在從 Git 下載 (分支: {TARGET_BRANCH_OR_TAG})...")
            subprocess.run(["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)], check=True, capture_output=True)
            self._log_manager.log("SUCCESS", "✅ Git 倉庫下載完成。")

            # 步驟 1: 初始化資料庫
            self._log_manager.log("INFO", "🔩 步驟 1/4: 正在初始化資料庫...")
            db_script = project_path / "src" / "db" / "database.py"
            subprocess.run([sys.executable, str(db_script)], check=True, capture_output=True)
            self._log_manager.log("SUCCESS", "✅ 資料庫初始化完成。")

            # 步驟 2: 安裝依賴
            self._log_manager.log("INFO", "📦 步驟 2/4: 正在安裝依賴...")
            req_file = project_path / "requirements.txt"
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req_file)], check=True)
            self._log_manager.log("SUCCESS", "✅ 依賴安裝完成。")

            # 步驟 3: 注入金鑰 (背景)
            self._log_manager.log("INFO", "🔑 步驟 3/4: 正在背景注入 API 金鑰...")
            key_thread = threading.Thread(target=self._inject_keys_background, args=(project_path,), daemon=True)
            key_thread.start()

            # 步驟 4: 啟動 API 伺服器
            self._log_manager.log("INFO", "🚀 步驟 4/4: 正在啟動 API 伺服器...")
            launch_command = [sys.executable, "-m", "uvicorn", "src.api.api_server:app", "--host", "0.0.0.0", "--port", str(self.port)]
            process_env = os.environ.copy()
            process_env['PYTHONPATH'] = str(project_path) + os.pathsep + process_env.get('PYTHONPATH', '')
            self.server_process = subprocess.Popen(launch_command, cwd=str(project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=process_env)

            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", f"[API伺服器] {line.strip()}")
                if uvicorn_ready_pattern.search(line):
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", f"✅ 伺服器已在埠號 {self.port} 上就緒！")
                    self.server_ready_event.set()
                    break # 收到信號後退出迴圈，讓執行緒繼續監控

            # 繼續監控日誌直到停止
            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                self._log_manager.log("DEBUG", f"[API伺服器] {line.strip()}")

            return_code = self.server_process.wait()
            if not self.server_ready_event.is_set():
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", f"伺服器進程在就緒前已終止，返回碼: {return_code}。")
        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"ServerManager 執行緒出錯: {e}")
        finally:
            self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止伺服器...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
                self.server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGKILL)
                except ProcessLookupError: pass

class TunnelManager:
    def __init__(self, log_manager, stats_dict, port):
        self._log = log_manager.log; self._stats = stats_dict; self._port = port
        self._stop_event = threading.Event(); self._threads = []; self._processes = []

    def start(self):
        if ENABLE_CLOUDFLARE: self._start_thread(self._run_cloudflared, "Cloudflare")
        if ENABLE_LOCALTUNNEL: self._start_thread(self._run_localtunnel, "Localtunnel")
        if ENABLE_COLAB_PROXY: self._start_thread(self._run_colab_proxy, "Colab")

    def _start_thread(self, target, name):
        thread = threading.Thread(target=target, name=name, daemon=True); self._threads.append(thread); thread.start()

    def _update_url(self, name, status, **kwargs):
        self._stats.setdefault('urls', {})[name] = {"status": status, **kwargs}

    def _run_cloudflared(self):
        self._update_url("Cloudflare", "starting", priority=2)
        if not Path("./cloudflared").is_file():
            arch = platform.machine()
            url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{'amd64' if arch == 'x86_64' else 'arm64'}"
            urllib.request.urlretrieve(url, "cloudflared"); os.chmod("cloudflared", 0o755)
        proc = subprocess.Popen(["./cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self._port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            if match := re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line):
                self._update_url("Cloudflare", "ready", url=match.group(0), priority=2); return

    def _run_localtunnel(self):
        self._update_url("Localtunnel", "starting", priority=3)
        if "localtunnel@" not in subprocess.run(["npm", "list", "-g", "localtunnel"], capture_output=True, text=True).stdout:
            subprocess.run(["npm", "install", "-g", "localtunnel"], check=True, capture_output=True)
        proc = subprocess.Popen(["npx", "localtunnel", "--port", str(self._port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            if match := re.search(r"your url is: (https://[a-zA-Z0-9-]+\.loca\.lt)", line):
                password = subprocess.run(["curl", "https://loca.lt/mytunnelpassword"], capture_output=True, text=True).stdout.strip()
                self._update_url("Localtunnel", "ready", url=match.group(1), password=password, priority=3); return

    def _run_colab_proxy(self):
        self._update_url("Colab", "starting", priority=1)
        try:
            url = colab_output.eval_js(f'google.colab.kernel.proxyPort({self._port})', timeout_sec=10)
            if url: self._update_url("Colab", "ready", url=url, priority=1)
        except Exception as e: self._log("WARN", f"Colab 代理啟動失敗: {e}")

    def stop(self):
        self._stop_event.set()
        for p in self._processes:
            if p.poll() is None: p.terminate()
        for t in self._threads: t.join(timeout=2)

# ==============================================================================
# SECTION 2: 主程式執行入口
# ==============================================================================
def main():
    start_time_monotonic = time.monotonic()
    shared_stats = {"start_time_monotonic": start_time_monotonic}
    log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE)
    server_manager = ServerManager(log_manager=log_manager, stats_dict=shared_stats)
    display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
    tunnel_manager = None
    try:
        display_manager.start()
        server_manager.start()
        if server_manager.server_ready_event.wait(timeout=SERVER_READY_TIMEOUT):
            log_manager.log("SUCCESS", f"✅ 後端服務已就緒，正在啟動代理通道...")
            tunnel_manager = TunnelManager(log_manager=log_manager, stats_dict=shared_stats, port=server_manager.port)
            tunnel_manager.start()
        else:
            log_manager.log("CRITICAL", f"伺服器在 {SERVER_READY_TIMEOUT} 秒內未能就緒。")
            raise SystemExit("Server did not start in time.")
        while server_manager._thread.is_alive(): time.sleep(1)
    except (KeyboardInterrupt, SystemExit) as e:
        log_manager.log("WARN", f"🛑 偵測到中斷信號: {e}")
    finally:
        if display_manager: display_manager.stop()
        if tunnel_manager: tunnel_manager.stop()
        if server_manager: server_manager.stop()
        clear_output()
        print("\n".join(display_manager._build_output_buffer()))
        print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")

if __name__ == "__main__":
    main()
