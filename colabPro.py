# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                      ║
# ║    ✨🐺 善狼一鍵啟動器 (v22.2) 🐺                                 ✨🐺 ║
# ║                                                                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║                                                                      ║
# ║ - V22.2 更新日誌 (2025-08-31):                                       ║
# ║   - **依賴修正**: 將 YouTube 下載依賴加入安裝列表，解決下載失敗問題。║
# ║   - **金鑰修正**: 修正了 Gemini API 金鑰的處理邏輯，使其在驗證後可  ║
# ║     被後續的模型列表功能使用。                                     ║
# ║   - **介面優化**: 將 Whisper 模型的預設選項調整為 'tiny'。         ║
# ║                                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

#@title ✨🐺 善狼一鍵啟動器 (v22.2) 🐺 { vertical-output: true, display-mode: "form" }
#@markdown ---
#@markdown ### **Part 1: 專案與環境設定**
#@markdown > **設定 Git 倉庫、分支或標籤，以及專案資料夾。**
#@markdown ---
#@markdown **後端程式碼倉庫 (REPOSITORY_URL)**
REPOSITORY_URL = "https://github.com/hsp1234-web/0808.git" #@param {type:"string"}
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "902" #@param {type:"string"}
#@markdown **專案資料夾名稱 (PROJECT_FOLDER_NAME)**
PROJECT_FOLDER_NAME = "wolf_project" #@param {type:"string"}
#@markdown **強制刷新後端程式碼 (FORCE_REPO_REFRESH)**
FORCE_REPO_REFRESH = True #@param {type:"boolean"}

#@markdown ---
#@markdown ### **Part 1.5: 通道啟用設定**
#@markdown > **選擇要啟動的公開存取通道。建議全部啟用以備不時之需。**
#@markdown ---
#@markdown **啟用 Colab 官方代理**
ENABLE_COLAB_PROXY = True #@param {type:"boolean"}
#@markdown **啟用 Localtunnel**
ENABLE_LOCALTUNNEL = True #@param {type:"boolean"}
#@markdown **啟用 Cloudflare**
ENABLE_CLOUDFLARE = True #@param {type:"boolean"}

#@markdown ---
#@markdown ### **Part 2: 儀表板與監控設定**
#@markdown > **設定儀表板的視覺與行為。**
#@markdown ---
#@markdown **儀表板更新頻率 (秒) (UI_REFRESH_SECONDS)**
UI_REFRESH_SECONDS = 0.5 #@param {type:"number"}
#@markdown **日誌顯示行數 (LOG_DISPLAY_LINES)**
LOG_DISPLAY_LINES = 10 #@param {type:"integer"}
#@markdown **時區設定 (TIMEZONE)**
TIMEZONE = "Asia/Taipei" #@param {type:"string"}

#@markdown ---
#@markdown ### **Part 3: 日誌等級可見性**
#@markdown > **勾選您想在儀表板上看到的日誌等級。**
#@markdown ---
SHOW_LOG_LEVEL_BATTLE = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_SUCCESS = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_INFO = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_WARN = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_ERROR = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_CRITICAL = True #@param {type:"boolean"}
SHOW_LOG_LEVEL_DEBUG = True #@param {type:"boolean"}

#@markdown ---
#@markdown ### **Part 4: 報告與歸檔設定**
#@markdown > **設定在任務結束時如何儲存報告。**
#@markdown ---
#@markdown **日誌歸檔資料夾 (LOG_ARCHIVE_ROOT_FOLDER)**
LOG_ARCHIVE_ROOT_FOLDER = "paper" #@param {type:"string"}
#@markdown **伺服器就緒等待超時 (秒) (SERVER_READY_TIMEOUT)**
SERVER_READY_TIMEOUT = 45 #@param {type:"integer"}
#@markdown **最大日誌複製數量 (LOG_COPY_MAX_LINES)**
LOG_COPY_MAX_LINES = 5000 #@param {type:"integer"}


#@markdown ---
#@markdown > **設定完成後，點擊此儲存格左側的「執行」按鈕。**
#@markdown ---

# ==============================================================================
# SECTION 0: 環境準備與核心依賴導入
# ==============================================================================
import sys
import subprocess
import socket
import platform
import urllib.request
try:
    import pytz
except ImportError:
    print("正在安裝 pytz...")
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
import json
import html
from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output, userdata

# ==============================================================================
# SECTION 1: 管理器類別定義 (Managers)
# ==============================================================================

class LogManager:
    """日誌管理器：負責記錄、過濾和儲存所有日誌訊息。"""
    def __init__(self, max_lines, timezone_str, log_levels_to_show):
        self._log_deque = deque(maxlen=max_lines)
        self._full_history = []
        self._lock = threading.Lock()
        self.timezone = pytz.timezone(timezone_str)
        self.log_levels_to_show = log_levels_to_show

    def log(self, level: str, message: str, source: str = "SYSTEM"):
        with self._lock:
            log_entry = {"timestamp": datetime.now(self.timezone), "level": level.upper(), "message": str(message), "source": source}
            self._log_deque.append(log_entry)
            self._full_history.append(log_entry)

    def get_display_logs(self) -> list:
        with self._lock:
            all_logs = list(self._log_deque)
            return [log for log in all_logs if self.log_levels_to_show.get(f"SHOW_LOG_LEVEL_{log['level']}", False)]

    def get_full_history(self) -> list:
        with self._lock:
            return self._full_history

ANSI_COLORS = {
    "SUCCESS": "\033[32m", "WARN": "\033[33m", "ERROR": "\033[31m",
    "CRITICAL": "\033[31m", "RESET": "\033[0m"
}

def colorize(text, level):
    return f"{ANSI_COLORS.get(level, '')}{text}{ANSI_COLORS['RESET']}"

class DisplayManager:
    """顯示管理器：在背景執行緒中負責繪製純文字動態儀表板。"""
    def __init__(self, log_manager, stats_dict, refresh_rate):
        self._log_manager = log_manager
        self._stats = stats_dict
        self._refresh_rate = refresh_rate
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _build_output_buffer(self) -> list[str]:
        output_buffer = ["✨🐺 善狼一鍵啟動器 (v21.1) 🐺", ""]
        logs_to_display = self._log_manager.get_display_logs()
        for log in logs_to_display:
            ts = log['timestamp'].strftime('%H:%M:%S')
            level, msg = log['level'], log['message']
            output_buffer.append(f"[{ts}] {colorize(f'[{level:^8}]', level)} {msg}")

        urls = self._stats.get('urls', {})
        if urls:
            if logs_to_display: output_buffer.append("")
            output_buffer.append("🔗 公開存取網址 (Public URLs):")
            sorted_urls = sorted(urls.items(), key=lambda item: item[1].get('priority', 99))
            for name, url_info in sorted_urls:
                if url_info['status'] == 'ready':
                    line = f"  - {name}: {colorize(url_info['url'], 'SUCCESS')}"
                    if 'password' in url_info:
                        line += f" (密碼: {url_info['password']})"
                    output_buffer.append(line)
                elif url_info['status'] == 'starting':
                    output_buffer.append(f"  - {name}: 正在啟動中...")
                else:
                    output_buffer.append(f"  - {name}: {colorize(url_info.get('error', '發生錯誤'), 'ERROR')}")

        try:
            import psutil
            cpu, ram = f"{psutil.cpu_percent():5.1f}%", f"{psutil.virtual_memory().percent:5.1f}%"
        except ImportError:
            cpu, ram = "  N/A ", "  N/A "
        elapsed = time.monotonic() - self._stats.get("start_time_monotonic", time.monotonic())
        mins, secs = divmod(elapsed, 60)
        output_buffer.append("")
        output_buffer.append(f"⏱️ {int(mins):02d}分{int(secs):02d}秒 | 💻 CPU: {cpu} | 🧠 RAM: {ram} | 🔥 狀態: {self._stats.get('status', '初始化...')}")
        return output_buffer

    def _run(self):
        while not self._stop_event.is_set():
            try:
                clear_output(wait=True)
                print("\n".join(self._build_output_buffer()), flush=True)
                time.sleep(self._refresh_rate)
            except Exception as e:
                self._log_manager.log("ERROR", f"DisplayManager 執行緒發生錯誤: {e}")
                time.sleep(5)

    def start(self): self._thread.start()
    def stop(self): self._stop_event.set(); self._thread.join(timeout=2)

class ServerManager:
    """伺服器管理器：負責啟動、停止和監控 Uvicorn 子進程。"""
    def __init__(self, log_manager, stats_dict):
        self._log_manager = log_manager; self._stats = stats_dict
        self.server_process = None; self.server_ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = None

    def _run(self):
        try:
            self._stats['status'] = "🚀 呼叫核心協調器..."
            self._log_manager.log("BATTLE", "=== 正在呼叫核心協調器 `orchestrator.py` ===")
            project_path = Path(PROJECT_FOLDER_NAME)
            if FORCE_REPO_REFRESH and project_path.exists():
                self._log_manager.log("INFO", f"偵測到舊的專案資料夾 '{project_path}'，正在強制刪除...")
                shutil.rmtree(project_path)

            self._log_manager.log("INFO", f"正在從 Git 下載 (分支: {TARGET_BRANCH_OR_TAG})...")
            git_command = ["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)]
            result = subprocess.run(git_command, check=False, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                error_message = f"""Git clone 失敗! 返回碼: {result.returncode}
--- STDOUT ---
{result.stdout}
--- STDERR ---
{result.stderr}
"""
                self._log_manager.log("CRITICAL", error_message)
                return

            self._log_manager.log("INFO", "✅ Git 倉庫下載完成。")
            project_src_path = project_path / "src"
            project_src_path_str = str(project_src_path.resolve())
            if project_src_path_str not in sys.path:
                sys.path.insert(0, project_src_path_str)

            from db.database import initialize_database, add_system_log
            initialize_database()
            add_system_log("colab_setup", "INFO", "Git repository cloned successfully.")

            # --- JULES: 重構為兩階段依賴安裝 ---

            def install_requirements(req_files, log_prefix=""):
                """幫助函式：智慧地檢查並只安裝缺失的依賴。"""
                self._log_manager.log("INFO", f"[{log_prefix}] 開始檢查依賴...")

                checker_script = project_path / "scripts" / "check_deps.py"
                if not checker_script.is_file():
                    self._log_manager.log("CRITICAL", f"[{log_prefix}] 依賴檢查腳本 'check_deps.py' 不存在！")
                    raise FileNotFoundError("Dependency checker script not found.")

                # 將檔案路徑轉換為字串列表以供 subprocess 使用
                req_file_paths = [str(p.resolve()) for p in req_files if p.is_file()]

                if not req_file_paths:
                    self._log_manager.log("INFO", f"[{log_prefix}] 找不到任何有效的依賴檔案。")
                    return

                # 執行依賴檢查腳本
                check_command = [sys.executable, str(checker_script.resolve())] + req_file_paths
                result = subprocess.run(check_command, capture_output=True, text=True, encoding='utf-8')

                if result.returncode != 0:
                    self._log_manager.log("ERROR", f"[{log_prefix}] 依賴檢查腳本執行失敗: {result.stderr}")
                    # 作為備用方案，直接安裝所有套件
                    missing_packages = [p.read_text(encoding='utf-8') for p in req_files]
                else:
                    missing_packages = result.stdout.strip().splitlines()

                if not missing_packages:
                    self._log_manager.log("SUCCESS", f"✅ [{log_prefix}] 所有依賴均已滿足，無需安裝。")
                    return

                self._log_manager.log("INFO", f"[{log_prefix}] 偵測到 {len(missing_packages)} 個缺失的套件，開始安裝...")

                # 將缺失的套件寫入臨時檔案
                temp_req_path = project_path / f"requirements_missing_{log_prefix.lower().replace(' ', '_')}.txt"
                with open(temp_req_path, "w", encoding="utf-8") as f:
                    for pkg in missing_packages:
                        f.write(pkg + "\n")

                try:
                    pip_command = [sys.executable, "-m", "pip", "install", "-q", "--progress-bar", "off", "-r", str(temp_req_path)]
                    try:
                        subprocess.check_call([sys.executable, "-m", "uv", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        pip_command = [sys.executable, "-m", "uv", "pip", "install", "--system", "-q", "-r", str(temp_req_path)]
                        self._log_manager.log("INFO", f"[{log_prefix}] 使用 'uv' 進行快速安裝...")
                    except (subprocess.CalledProcessError, FileNotFoundError):
                        self._log_manager.log("INFO", f"[{log_prefix}] 未找到 'uv'，退回使用 'pip'。")

                    subprocess.check_call(pip_command)
                    self._log_manager.log("SUCCESS", f"✅ {log_prefix} 依賴安裝完成。")
                except subprocess.CalledProcessError as e:
                    error_message = f"[{log_prefix}] 依賴安裝失敗！返回碼: {e.returncode}\n--- STDOUT ---\n{e.stdout}\n--- STDERR ---\n{e.stderr}"
                    self._log_manager.log("CRITICAL", error_message)
                    raise
                finally:
                    if temp_req_path.exists():
                        temp_req_path.unlink()

            # --- 階段 1: 同步安裝核心依賴 ---
            self._log_manager.log("INFO", "步驟 1/3: 正在快速安裝核心伺服器依賴...")
            core_requirements = [
                project_path / "requirements" / "server.txt",
                project_path / "requirements" / "youtube.txt"
            ]
            install_requirements(core_requirements, "核心依賴")

            # --- 階段 2: 啟動後端服務 (這會立即發生，以便使用者盡快取得 URL) ---
            self._log_manager.log("INFO", "步驟 2/3: 正在啟動後端服務...")
            launch_command = [sys.executable, "src/core/orchestrator.py"]
            process_env = os.environ.copy()
            src_path_str = str((project_path / "src").resolve())
            process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}".strip(os.pathsep)

            self.server_process = subprocess.Popen(launch_command, cwd=str(project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=process_env)

            # --- 階段 3: 在背景安裝大型依賴 ---
            def background_install():
                self._log_manager.log("INFO", "步驟 3/3: [背景] 開始安裝大型任務依賴...")
                large_requirements = [
                    project_path / "requirements" / "transcriber.txt",
                    project_path / "requirements" / "gemini.txt"
                ]
                try:
                    install_requirements(large_requirements, "背景大型任務")
                    self._log_manager.log("SUCCESS", "[背景] ✅ 所有大型任務依賴均已成功安裝！")
                except Exception as e:
                    self._log_manager.log("CRITICAL", f"[背景] 大型依賴安裝失敗: {e}")

            bg_install_thread = threading.Thread(target=background_install, daemon=True)
            bg_install_thread.start()

            port_pattern = re.compile(r"PROXY_URL: http://127.0.0.1:(\d+)")
            uvicorn_ready_pattern = re.compile(r"Uvicorn running on")
            server_ready = False

            for line in iter(self.server_process.stdout.readline, ''):
                if self._stop_event.is_set(): break
                line = line.strip()
                self._log_manager.log("DEBUG", line)
                if not self.port and (match := port_pattern.search(line)):
                    self.port = int(match.group(1))
                    self._log_manager.log("INFO", f"✅ 從日誌中成功解析出 API 埠號: {self.port}")
                if not server_ready and uvicorn_ready_pattern.search(line):
                    server_ready = True
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", "伺服器已就緒！收到 Uvicorn 握手信號！")
                if self.port and server_ready:
                    self.server_ready_event.set()

            return_code = self.server_process.wait()
            if not self.server_ready_event.is_set():
                self._stats['status'] = "❌ 伺服器啟動失敗"
                self._log_manager.log("CRITICAL", f"協調器進程在就緒前已終止，返回碼: {return_code}。請檢查上方日誌以了解詳細錯誤。")
        except Exception as e: self._stats['status'] = "❌ 發生致命錯誤"; self._log_manager.log("CRITICAL", f"ServerManager 執行緒出錯: {e}")
        finally: self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止伺服器進程...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
                self.server_process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try: os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGKILL)
                except ProcessLookupError: pass
        self._thread.join(timeout=2)

class TunnelManager:
    """通道管理器：並行啟動多個代理通道 (Cloudflare, Localtunnel) 以提供備援。"""
    def __init__(self, log_manager, stats_dict, port):
        self._log = log_manager.log; self._stats = stats_dict; self._port = port
        self._stop_event = threading.Event(); self._threads = []; self._processes = []

    def start(self):
        if ENABLE_CLOUDFLARE: self._start_thread(self._run_cloudflared, "Cloudflare")
        if ENABLE_LOCALTUNNEL: self._start_thread(self._run_localtunnel, "Localtunnel")
        if ENABLE_COLAB_PROXY: self._start_thread(self._run_colab_proxy, "Colab")

    def _start_thread(self, target, name):
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._threads.append(thread); thread.start()

    def _update_url_status(self, name, status, url=None, error=None, priority=99, password=None):
        with self._stats.get('_lock', threading.Lock()):
            entry = {"status": status, "priority": priority}
            if url: entry["url"] = url
            if error: entry["error"] = error
            if password: entry["password"] = password
            self._stats.setdefault('urls', {})[name] = entry

    def _ensure_cloudflared_installed(self):
        if Path("./cloudflared").is_file(): return True
        self._log("INFO", "未找到 Cloudflared，正在下載...", "Cloudflare")
        arch = platform.machine()
        url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{'amd64' if arch == 'x86_64' else 'arm64'}"
        try:
            urllib.request.urlretrieve(url, "cloudflared"); os.chmod("cloudflared", 0o755)
            self._log("SUCCESS", "✅ Cloudflared 下載成功。", "Cloudflare"); return True
        except Exception as e: self._log("ERROR", f"Cloudflared 下載失敗: {e}", "Cloudflare"); return False

    def _run_cloudflared(self):
        self._update_url_status("Cloudflare", "starting", priority=2)
        if not self._ensure_cloudflared_installed(): self._update_url_status("Cloudflare", "error", error="安裝失敗"); return
        proc = subprocess.Popen(["./cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self._port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            self._log("DEBUG", line.strip(), "Cloudflare")
            if match := url_pattern.search(line):
                self._update_url_status("Cloudflare", "ready", url=match.group(0), priority=2); return
        if not self._stop_event.is_set(): self._update_url_status("Cloudflare", "error", error="無法從日誌中解析 URL")

    def _ensure_localtunnel_installed(self):
        if "localtunnel@" in subprocess.run(["npm", "list", "-g", "localtunnel"], capture_output=True, text=True).stdout: return True
        self._log("INFO", "正在安裝 Localtunnel...", "Localtunnel")
        try:
            subprocess.run(["npm", "install", "-g", "localtunnel"], check=True, capture_output=True)
            self._log("SUCCESS", "✅ Localtunnel 安裝成功。", "Localtunnel"); return True
        except subprocess.CalledProcessError as e: self._log("ERROR", f"Localtunnel 安裝失敗: {e.stderr}", "Localtunnel"); return False

    def _run_localtunnel(self):
        self._update_url_status("Localtunnel", "starting", priority=3)
        if not self._ensure_localtunnel_installed(): self._update_url_status("Localtunnel", "error", error="安裝失敗"); return
        proc = subprocess.Popen(["npx", "localtunnel", "--port", str(self._port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        url_pattern = re.compile(r"your url is: (https://[a-zA-Z0-9-]+\.loca\.lt)")
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            self._log("DEBUG", line.strip(), "Localtunnel")
            if match := url_pattern.search(line):
                self._update_url_status("Localtunnel", "ready", url=match.group(1), priority=3); return
        if not self._stop_event.is_set(): self._update_url_status("Localtunnel", "error", error="無法從日誌中解析 URL")

    def _run_colab_proxy(self):
        self._update_url_status("Colab", "starting", priority=1)
        for attempt in range(10):
            if self._stop_event.is_set(): return
            try:
                url = colab_output.eval_js(f'google.colab.kernel.proxyPort({self._port})', timeout_sec=10)
                if url and url.strip(): self._update_url_status("Colab", "ready", url=url, priority=1); return
                self._log("WARN", f"Colab 代理嘗試 #{attempt+1} 返回空 URL。", "Colab")
            except Exception as e: self._log("WARN", f"Colab 代理嘗試 #{attempt+1} 失敗: {e}", "Colab")
            time.sleep(2)
        self._update_url_status("Colab", "error", error="重試 10 次後失敗")

    def stop(self):
        self._stop_event.set()
        for p in self._processes:
            if p.poll() is None:
                try: p.terminate()
                except ProcessLookupError: pass
        for t in self._threads: t.join(timeout=2)

# ==============================================================================
# SECTION 2: 核心功能函式
# ==============================================================================
def create_log_viewer_html(log_manager, display_manager):
    """ 產生最終的 HTML 日誌報告，採納 v15 的 textarea 方案以增強穩定性。 """
    try:
        full_log_history = [f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in log_manager.get_full_history()]
        screen_output = "\n".join(display_manager._build_output_buffer())

        log_to_display = "\n".join(full_log_history[-LOG_COPY_MAX_LINES:])

        escaped_log_for_textarea = html.escape(log_to_display)
        escaped_screen_for_textarea = html.escape(screen_output)

        screen_id = f"screen-area-{int(time.time() * 1000)}"
        log_id = f"log-area-{int(time.time() * 1000)}"

        return f'''
            <style>
                .collapsible-log {{ margin-top: 15px; margin-bottom: 15px; border: 1px solid #e0e0e0; padding: 12px; border-radius: 8px; background-color: #fafafa; }}
                .collapsible-log summary {{ cursor: pointer; font-weight: bold; color: #333; }}
                .collapsible-log pre {{ background-color: #fff; padding: 12px; border: 1px solid #e0e0e0; border-radius: 5px; white-space: pre-wrap; word-wrap: break-word; font-family: monospace; font-size: 13px; color: #444; max-height: 400px; overflow-y: auto; }}
                .copy-button {{ padding: 8px 16px; margin: 5px; cursor: pointer; border: 1px solid #ccc; border-radius: 5px; background-color: #f0f0f0; font-family: sans-serif; }}
                .copy-button:hover {{ background-color: #e0e0e0; }}
            </style>
            <script>
                function copyFromTextarea(elementId, button) {{
                    const ta = document.getElementById(elementId);
                    if (!ta) {{ console.error("Textarea not found:", elementId); return; }}
                    navigator.clipboard.writeText(ta.value).then(() => {{
                        const originalText = button.innerText;
                        button.innerText = "✅ 已複製!";
                        setTimeout(() => {{ button.innerText = originalText; }}, 2000);
                    }}, (err) => {{
                        button.innerText = "❌ 複製失敗";
                        console.error('複製失敗: ', err);
                    }});
                }}
            </script>

            <textarea id="{screen_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_screen_for_textarea}</textarea>
            <textarea id="{log_id}" style="position:absolute; left: -9999px; top: -9999px;" readonly>{escaped_log_for_textarea}</textarea>

            <div>
                <button class="copy-button" onclick="copyFromTextarea('{screen_id}', this)">📋 複製上方最終畫面</button>
            </div>
            <details class="collapsible-log">
                <summary>點此展開/收合最近 {len(full_log_history[-LOG_COPY_MAX_LINES:])} 條詳細日誌</summary>
                <div style="margin-top: 12px;">
                    <button class="copy-button" onclick="copyFromTextarea('{log_id}', this)">📄 複製下方完整日誌</button>
                    <pre><code>{escaped_log_for_textarea}</code></pre>
                    <button class="copy-button" onclick="copyFromTextarea('{log_id}', this)">📄 複製下方完整日誌</button>
                </div>
            </details>
        '''
    except Exception as e:
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

def archive_reports(log_manager, start_time, end_time, status):
    print("\n\n" + "="*60 + "\n--- 任務結束，開始執行自動歸檔 ---\n" + "="*60)
    try:
        root_folder = Path(LOG_ARCHIVE_ROOT_FOLDER)
        root_folder.mkdir(exist_ok=True)
        ts_folder_name = start_time.strftime('%Y-%m-%dT%H-%M-%S%z')
        report_dir = root_folder / ts_folder_name
        report_dir.mkdir(exist_ok=True)
        log_history = log_manager.get_full_history()
        detailed_log_content = f"# 詳細日誌\n\n```\n" + "\n".join([f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in log_history]) + "\n```"
        (report_dir / "詳細日誌.md").write_text(detailed_log_content, encoding='utf-8')
        duration = end_time - start_time
        perf_report_content = f"# 效能報告\n\n- **任務狀態**: {status}\n- **開始時間**: `{start_time.isoformat()}`\n- **結束時間**: `{end_time.isoformat()}`\n- **總耗時**: `{str(duration)}`\n"
        (report_dir / "效能報告.md").write_text(perf_report_content.strip(), encoding='utf-8')
        (report_dir / "綜合報告.md").write_text(f"# 綜合報告\n\n{perf_report_content}\n{detailed_log_content}", encoding='utf-8')
        print(f"✅ 報告已成功歸檔至: {report_dir}")
    except Exception as e: print(f"❌ 歸檔報告時發生錯誤: {e}")

# ==============================================================================
# SECTION 2.5: 安裝系統級依賴 (FFmpeg)
# ==============================================================================
print("檢查並安裝系統級依賴 FFmpeg...")
try:
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        print("未偵測到 FFmpeg，開始安裝...")
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
        print("✅ FFmpeg 安裝完成。")
    else:
        print("✅ FFmpeg 已安裝。")
except Exception as e:
    print(f"❌ 安裝 FFmpeg 時發生錯誤: {e}")

# ==============================================================================
# SECTION 3: 主程式執行入口
# ==============================================================================
def main():
    shared_stats = {"start_time_monotonic": time.monotonic(), "status": "初始化...", "urls": {}}
    log_manager, display_manager, server_manager, tunnel_manager = None, None, None, None
    start_time = datetime.now(pytz.timezone(TIMEZONE))
    try:
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels)
        server_manager = ServerManager(log_manager=log_manager, stats_dict=shared_stats)
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)
        display_manager.start()
        server_manager.start()
        if server_manager.server_ready_event.wait(timeout=SERVER_READY_TIMEOUT):
            if not server_manager.port:
                log_manager.log("CRITICAL", "伺服器已就緒，但未能解析出 API 埠號。無法建立代理連結。")
            else:
                log_manager.log("SUCCESS", f"✅ 後端服務已在埠號 {server_manager.port} 上就緒，正在啟動所有代理通道...")
                tunnel_manager = TunnelManager(log_manager=log_manager, stats_dict=shared_stats, port=server_manager.port)
                tunnel_manager.start()
        else:
            shared_stats['status'] = "❌ 伺服器啟動超時"
            log_manager.log("CRITICAL", f"伺服器在 {SERVER_READY_TIMEOUT} 秒內未能就緒。")
        while server_manager._thread.is_alive(): time.sleep(1)
    except KeyboardInterrupt:
        if log_manager: log_manager.log("WARN", "🛑 偵測到使用者手動中斷...")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
        else: print(f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        if display_manager and display_manager._thread.is_alive(): display_manager.stop()
        if 'tunnel_manager' in locals() and tunnel_manager: tunnel_manager.stop()
        if server_manager: server_manager.stop()
        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")
            display(HTML(create_log_viewer_html(log_manager, display_manager)))
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

if __name__ == "__main__":
    main()
