# -*- coding: utf-8 -*-
# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                      ║
# ║   ✨🐺 善狼一鍵啟動器 (v23.1) 🐺                                ✨🐺 ║
# ║                                                                      ║
# ╠══════════════════════════════════════════════════════════════════╣
# ║                                                                      ║
# ║ - V23.1 更新日誌 (2025-09-10):                                       ║
# ║   - **啟動優化**: 重構依賴安裝流程，優先載入核心服務，將大型功能套件 ║
# ║     改為背景安裝，大幅縮短伺服器可見時間。                             ║
# ║   - **安裝加速**: 新增 `uv` 安裝程序，確保在可用時使用其取代 pip     ║
# ║     以加速依賴下載。                                                 ║
# ║   - **配置更新**: 將預設分支更新為 `main` 以支援最新 MPA 架構。      ║
# ║                                                                      ║
# ╚══════════════════════════════════════════════════════════════════╝

#@title ✨🐺 善狼一鍵啟動器 (v23.1) - 極簡版 🐺 { vertical-output: true, display-mode: "form" }
#@markdown ---
#@markdown ### **唯一設定：後端版本**
#@markdown > **請在此輸入您想使用的後端版本分支或標籤。**
#@markdown ---
#@markdown **後端版本分支或標籤 (TARGET_BRANCH_OR_TAG)**
TARGET_BRANCH_OR_TAG = "9" #@param {type:"string"}
#@markdown ---
#@markdown > **設定完成後，點擊「執行」按鈕。**
#@markdown > **所有其他設定（如 Git 倉庫）均已移至程式碼內部。**
#@markdown ---

# ==============================================================================
# SECTION A: 進階設定 (可在此處修改)
# 說明：以下為不常變動的進階設定。若需調整，請直接修改此區塊的變數值。
# ==============================================================================

# Part 1: 核心專案設定
REPOSITORY_URL = "https://github.com/hsp1234-web/20250910.git"
PROJECT_FOLDER_NAME = "wolf_project"
FORCE_REPO_REFRESH = True

# Part 2: 通道啟用設定
ENABLE_COLAB_PROXY = True
ENABLE_LOCALTUNNEL = True
ENABLE_CLOUDFLARE = True

# Part 3: 儀表板與監控設定
UI_REFRESH_SECONDS = 0.5
LOG_DISPLAY_LINES = 10
TIMEZONE = "Asia/Taipei"

# Part 4: 日誌等級可見性
SHOW_LOG_LEVEL_BATTLE = True
SHOW_LOG_LEVEL_SUCCESS = True
SHOW_LOG_LEVEL_INFO = True
SHOW_LOG_LEVEL_WARN = True
SHOW_LOG_LEVEL_ERROR = True
SHOW_LOG_LEVEL_CRITICAL = True
SHOW_LOG_LEVEL_DEBUG = True

# Part 5: API 金鑰載入設定 (整合 Colab Secrets)
# 說明：系統會從 Colab Secrets 讀取金鑰。請使用以下一或兩種方式設定。
# 方式一：依數量載入 (推薦)。根據 GOOGLE_API_KEY, GOOGLE_API_KEY_1... 的命名慣例載入。
# 例如：設為 5 將會嘗試載入 GOOGLE_API_KEY 到 GOOGLE_API_KEY_5，共 6 組。
KEY_LOAD_COUNT_LIMIT = 5
# 方式二：依名稱自訂。如果您有不符合命名慣例的金鑰，請在此處填寫，並用逗號分隔。
# 例如："MY_PERSONAL_KEY, PROJECT_X_KEY"
CUSTOM_SECRETS_NAMES = ""

# Part 6: 報告與歸檔設定
LOG_ARCHIVE_ROOT_FOLDER = "paper"
SERVER_READY_TIMEOUT = 60
LOG_COPY_MAX_LINES = 5000

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
from collections import deque, namedtuple
import re
import json
import html
from typing import List, Tuple, Optional

from IPython.display import clear_output, display, HTML
from google.colab import output as colab_output, userdata, drive

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
        output_buffer = ["✨🐺 善狼一鍵啟動器 (v23.1) 🐺", ""]
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
    def __init__(self, log_manager, stats_dict, api_keys_json: str = "[]"):
        self._log_manager = log_manager
        self._stats = stats_dict
        self.server_process = None
        self.server_ready_event = threading.Event()
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.port = None
        self._api_keys_json = api_keys_json

    def _ensure_uv_installed(self):
        """檢查 `uv` 是否已安裝，若否，則嘗試安裝。"""
        try:
            subprocess.check_call([sys.executable, "-m", "uv", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._log_manager.log("INFO", "✅ 'uv' 加速器已安裝。")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            self._log_manager.log("INFO", "未找到 'uv'，正在嘗試安裝...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "uv"])
                self._log_manager.log("SUCCESS", "✅ 'uv' 加速器安裝成功！")
                return True
            except subprocess.CalledProcessError:
                self._log_manager.log("WARN", "安裝 'uv' 失敗，將退回使用 'pip'。")
                return False

    def _run(self):
        try:
            self._log_manager.log("BATTLE", "=== 啟動器核心流程開始 ===")
            self._stats['status'] = "🚀 準備執行環境..."
            project_path = Path(PROJECT_FOLDER_NAME)
            if FORCE_REPO_REFRESH and project_path.exists():
                self._log_manager.log("INFO", f"偵測到舊的專案資料夾 '{project_path}'，正在強制刪除...")
                shutil.rmtree(project_path)

            self._log_manager.log("INFO", f"正在從 Git 下載 (分支: {TARGET_BRANCH_OR_TAG})...")
            git_command = ["git", "clone", "--branch", TARGET_BRANCH_OR_TAG, "--depth", "1", REPOSITORY_URL, str(project_path)]
            result = subprocess.run(git_command, check=False, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                error_message = f"Git clone 失敗! 返回碼: {result.returncode}\n--- STDOUT ---\n{result.stdout}\n--- STDERR ---\n{result.stderr}"
                self._log_manager.log("CRITICAL", error_message)
                return

            self._log_manager.log("INFO", "✅ Git 倉庫下載完成。")
            project_src_path = project_path / "src"
            sys.path.insert(0, str(project_src_path.resolve()))

            from db.database import initialize_database
            initialize_database()

            use_uv = self._ensure_uv_installed()

            def install_requirements(req_files, log_prefix=""):
                self._log_manager.log("INFO", f"[{log_prefix}] 開始檢查與安裝依賴...")
                checker_script = project_path / "scripts" / "check_deps.py"
                if not checker_script.is_file():
                    raise FileNotFoundError(f"[{log_prefix}] 依賴檢查腳本 'check_deps.py' 不存在！")

                req_file_paths = [str(p.resolve()) for p in req_files if p.is_file()]
                if not req_file_paths:
                    self._log_manager.log("INFO", f"[{log_prefix}] 找不到任何有效的依賴檔案。")
                    return

                check_command = [sys.executable, str(checker_script.resolve())] + req_file_paths
                result = subprocess.run(check_command, capture_output=True, text=True, encoding='utf-8')

                if result.returncode != 0:
                    self._log_manager.log("WARN", f"[{log_prefix}] 依賴檢查腳本執行失敗，將安裝所有套件。")
                    missing_packages_text = "".join([p.read_text(encoding='utf-8') for p in req_files])
                    missing_packages = missing_packages_text.strip().splitlines()
                else:
                    missing_packages = result.stdout.strip().splitlines()

                if not missing_packages:
                    self._log_manager.log("SUCCESS", f"✅ [{log_prefix}] 所有依賴均已滿足。")
                    return

                self._log_manager.log("INFO", f"[{log_prefix}] 偵測到 {len(missing_packages)} 個缺失的套件，開始安裝...")
                temp_req_path = project_path / f"requirements_missing.txt"
                with open(temp_req_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(missing_packages))

                try:
                    installer = "uv" if use_uv else "pip"
                    pip_command = [sys.executable, "-m", installer, "pip", "install", "--system", "-q", "-r", str(temp_req_path)] if use_uv else [sys.executable, "-m", "pip", "install", "-q", "-r", str(temp_req_path)]
                    subprocess.check_call(pip_command)
                    self._log_manager.log("SUCCESS", f"✅ [{log_prefix}] 依賴安裝完成。")
                finally:
                    if temp_req_path.exists(): temp_req_path.unlink()

            self._log_manager.log("INFO", "步驟 1/3: 正在安裝核心伺服器依賴...")
            install_requirements([project_path / "requirements" / "core.txt"], "核心伺服器")

            self._log_manager.log("INFO", "步驟 2/3: 正在啟動後端協調器...")
            launch_command = [sys.executable, "src/core/orchestrator.py"]
            process_env = os.environ.copy()
            process_env['PYTHONPATH'] = f"{str(project_src_path.resolve())}{os.pathsep}{process_env.get('PYTHONPATH', '')}"
            process_env['GOOGLE_API_KEYS_JSON'] = self._api_keys_json

            self.server_process = subprocess.Popen(launch_command, cwd=str(project_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', preexec_fn=os.setsid, env=process_env)

            def background_install():
                self._log_manager.log("INFO", "步驟 3/3: [背景] 開始安裝大型與功能性依賴...")
                all_reqs = (project_path / "requirements").glob("*.txt")
                large_reqs = [p for p in all_reqs if p.name not in ["core.txt", "test.txt"]]
                try:
                    install_requirements(large_reqs, "功能與模型")
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
                self._log_manager.log("DEBUG", line, "Orchestrator")
                if not self.port and (match := port_pattern.search(line)):
                    self.port = int(match.group(1))
                    self._log_manager.log("INFO", f"✅ 從日誌中成功解析出 API 埠號: {self.port}")
                if not server_ready and uvicorn_ready_pattern.search(line):
                    server_ready = True
                    self._stats['status'] = "✅ 伺服器運行中"
                    self._log_manager.log("SUCCESS", f"✅ 伺服器已就緒！ (總耗時: {time.monotonic() - self._stats.get('start_time_monotonic', 0):.2f} 秒)")
                if self.port and server_ready:
                    self.server_ready_event.set()

            if not self.server_ready_event.is_set():
                self._stats['status'] = "❌ 伺服器啟動失敗"
        except Exception as e:
            self._stats['status'] = "❌ 發生致命錯誤"
            self._log_manager.log("CRITICAL", f"ServerManager 執行緒出錯: {e}")
        finally:
            self._stats['status'] = "⏹️ 已停止"

    def start(self): self._thread.start()
    def stop(self):
        self._stop_event.set()
        if self.server_process and self.server_process.poll() is None:
            self._log_manager.log("INFO", "正在終止伺服器進程...")
            try:
                os.killpg(os.getpgid(self.server_process.pid), subprocess.signal.SIGTERM)
            except ProcessLookupError: pass
        self._thread.join(timeout=2)

class TunnelManager:
    """通道管理器：並行啟動多個代理通道。"""
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

    def _update_url_status(self, name, status, url=None, error=None, priority=99):
        with self._stats.get('_lock', threading.Lock()):
            self._stats.setdefault('urls', {})[name] = {"status": status, "url": url, "error": error, "priority": priority}

    def _run_cloudflared(self):
        self._update_url_status("Cloudflare", "starting", priority=2)
        if not Path("./cloudflared").is_file():
            arch = platform.machine()
            url = f"https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-{'amd64' if arch == 'x86_64' else 'arm64'}"
            try:
                urllib.request.urlretrieve(url, "cloudflared"); os.chmod("cloudflared", 0o755)
            except Exception as e:
                self._update_url_status("Cloudflare", "error", error=f"安裝失敗: {e}", priority=2); return

        proc = subprocess.Popen(["./cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self._port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        url_pattern = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            if match := url_pattern.search(line):
                self._update_url_status("Cloudflare", "ready", url=match.group(0), priority=2); return
        if not self._stop_event.is_set(): self._update_url_status("Cloudflare", "error", error="無法解析 URL", priority=2)

    def _run_localtunnel(self):
        self._update_url_status("Localtunnel", "starting", priority=3)
        try:
            subprocess.run(["npm", "install", "-g", "localtunnel"], check=True, capture_output=True)
        except Exception as e:
            self._update_url_status("Localtunnel", "error", error=f"安裝失敗: {e}", priority=3); return

        proc = subprocess.Popen(["npx", "localtunnel", "--port", str(self._port)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
        self._processes.append(proc)
        url_pattern = re.compile(r"your url is: (https://[a-zA-Z0-9-]+\.loca\.lt)")
        for line in iter(proc.stdout.readline, ''):
            if self._stop_event.is_set(): break
            if match := url_pattern.search(line):
                self._update_url_status("Localtunnel", "ready", url=match.group(1), priority=3); return
        if not self._stop_event.is_set(): self._update_url_status("Localtunnel", "error", error="無法解析 URL", priority=3)

    def _run_colab_proxy(self):
        self._update_url_status("Colab", "starting", priority=1)
        try:
            url = colab_output.eval_js(f'google.colab.kernel.proxyPort({self._port})', timeout_sec=10)
            if url and url.strip():
                self._update_url_status("Colab", "ready", url=url, priority=1)
            else:
                self._update_url_status("Colab", "error", error="返回空 URL", priority=1)
        except Exception as e:
            self._update_url_status("Colab", "error", error=f"獲取失敗: {e}", priority=1)

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

ApiKey = namedtuple('ApiKey', ['value', 'name'])

def get_secret_with_retry(key_name: str, log_manager: LogManager) -> Tuple[Optional[str], Optional[str]]:
    """從 Colab Userdata 獲取金鑰。"""
    try:
        value = userdata.get(key_name)
        return (value, None) if value else (None, f"金鑰 '{key_name}' 不存在或為空。")
    except Exception as e:
        return None, f"讀取金鑰 '{key_name}' 時發生錯誤: {e}"

def pre_flight_checks(log_manager: LogManager) -> List[ApiKey]:
    """執行飛行前檢查：掛載 Drive 並從 Colab Secrets 載入 API 金鑰。"""
    log_manager.log("系統", "✈️ [PoC] 正在執行飛行前檢查...")

    try:
        drive.mount('/content/drive', force_remount=True)
        log_manager.log("Drive", "✅ Google Drive 掛載成功。")
    except Exception as e:
        log_manager.log("Drive", f"⚠️ 無法掛載 Google Drive: {e}，將繼續執行。")

    log_manager.log("金鑰管理", "正在根據使用者設定動態載入 API 金鑰...")

    target_key_names = set()
    try:
        k_limit = int(KEY_LOAD_COUNT_LIMIT)
        if 0 <= k_limit <= 15:
            names_by_count = ['GOOGLE_API_KEY'] + [f"GOOGLE_API_KEY_{i}" for i in range(1, k_limit + 1)]
            target_key_names.update(names_by_count)
            log_manager.log("金鑰管理", f"✅ (方式一) 已指定 {len(names_by_count)} 個金鑰。")
    except (NameError, ValueError, TypeError):
        log_manager.log("金鑰管理", f"⚠️ (方式一) 變數 'KEY_LOAD_COUNT_LIMIT' 設定無效。")

    try:
        if CUSTOM_SECRETS_NAMES and isinstance(CUSTOM_SECRETS_NAMES, str):
            names_by_custom = [name.strip() for name in CUSTOM_SECRETS_NAMES.split(',') if name.strip()]
            if names_by_custom:
                target_key_names.update(names_by_custom)
                log_manager.log("金鑰管理", f"✅ (方式二) 已新增 {len(names_by_custom)} 個自訂金鑰。")
    except NameError:
         log_manager.log("金鑰管理", f"⚠️ (方式二) 變數 'CUSTOM_SECRETS_NAMES' 未定義。")

    if not target_key_names:
        log_manager.log("金鑰管理", "⚠️ 未設定任何 API 金鑰，系統將在無金鑰模式下啟動。")
        return []

    final_target_list = sorted(list(target_key_names))
    log_manager.log("金鑰管理", f"🔎 預計讀取 {len(final_target_list)} 個金鑰: {final_target_list}")

    valid_keys = []
    for name in final_target_list:
        value, error = get_secret_with_retry(name, log_manager)
        if value:
            valid_keys.append(ApiKey(value, name))
        else:
            log_manager.log("金鑰管理", f"  -> 讀取金鑰 '{name}' 失敗，已跳過。")

    if not valid_keys:
        log_manager.log("金鑰管理", "⚠️ 未能從 Colab Secrets 載入任何有效金鑰。")
    else:
        log_manager.log("金鑰管理", f"✅ 共載入 {len(valid_keys)} 組有效的 API 金鑰。")
    return valid_keys

def create_log_viewer_html(log_manager, display_manager):
    try:
        full_log_history = [f"[{log['timestamp'].isoformat()}] [{log['level']}] {log['message']}" for log in log_manager.get_full_history()]
        screen_output = "\n".join(display_manager._build_output_buffer())
        log_to_display = "\n".join(full_log_history[-LOG_COPY_MAX_LINES:])
        escaped_log = html.escape(log_to_display)
        escaped_screen = html.escape(screen_output)
        screen_id, log_id = f"s-{time.time_ns()}", f"l-{time.time_ns()}"
        return f'''
            <style> .collapsible-log{{...}} .copy-button{{...}} </style>
            <script> function copyFromTextarea(id, btn){{...}} </script>
            <textarea id="{screen_id}" style="display:none;">{escaped_screen}</textarea>
            <textarea id="{log_id}" style="display:none;">{escaped_log}</textarea>
            <button class="copy-button" onclick="copyFromTextarea('{screen_id}', this)">📋 複製上方最終畫面</button>
            <details class="collapsible-log">
                <summary>點此展開/收合最近 {len(full_log_history[-LOG_COPY_MAX_LINES:])} 條詳細日誌</summary>
                <button class="copy-button" onclick="copyFromTextarea('{log_id}', this)">📄 複製下方完整日誌</button>
                <pre><code>{escaped_log}</code></pre>
            </details>
        '''
    except Exception as e:
        return f"<p>❌ 產生最終日誌報告時發生錯誤: {html.escape(str(e))}</p>"

def archive_reports(log_manager, start_time, end_time, status):
    print("\n--- 任務結束，開始執行自動歸檔 ---")
    try:
        root_folder = Path(LOG_ARCHIVE_ROOT_FOLDER)
        root_folder.mkdir(exist_ok=True)
        report_dir = root_folder / start_time.strftime('%Y-%m-%dT%H-%M-%S')
        report_dir.mkdir(exist_ok=True)
        log_history = log_manager.get_full_history()
        log_content = "# 詳細日誌\n\n```\n" + "\n".join([f"[{log['timestamp'].isoformat()}] {log['message']}" for log in log_history]) + "\n```"
        (report_dir / "詳細日誌.md").write_text(log_content, encoding='utf-8')
        print(f"✅ 報告已歸檔至: {report_dir}")
    except Exception as e: print(f"❌ 歸檔報告時發生錯誤: {e}")

# ==============================================================================
# SECTION 2.5: 安裝系統級依賴 (FFmpeg)
# ==============================================================================
print("檢查並安裝系統級依賴 FFmpeg...")
try:
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        subprocess.run(["apt-get", "update", "-qq"], check=True)
        subprocess.run(["apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
    print("✅ FFmpeg 已安裝。")
except Exception as e:
    print(f"❌ 安裝 FFmpeg 時發生錯誤: {e}")

# ==============================================================================
# SECTION 3: 主程式執行入口
# ==============================================================================
def main():
    start_time_monotonic = time.monotonic()
    shared_stats = {"start_time_monotonic": start_time_monotonic, "status": "初始化..."}
    log_manager, display_manager, server_manager, tunnel_manager = [None] * 4
    start_time = datetime.now(pytz.timezone(TIMEZONE))
    try:
        log_levels = {name: globals()[name] for name in globals() if name.startswith("SHOW_LOG_LEVEL_")}
        log_manager = LogManager(max_lines=LOG_DISPLAY_LINES, timezone_str=TIMEZONE, log_levels_to_show=log_levels)

        valid_keys = pre_flight_checks(log_manager)
        keys_for_json = [{'name': k.name, 'value': k.value} for k in valid_keys]
        keys_json_str = json.dumps(keys_for_json)

        server_manager = ServerManager(log_manager=log_manager, stats_dict=shared_stats, api_keys_json=keys_json_str)
        display_manager = DisplayManager(log_manager=log_manager, stats_dict=shared_stats, refresh_rate=UI_REFRESH_SECONDS)

        display_manager.start()
        server_manager.start()

        if server_manager.server_ready_event.wait(timeout=SERVER_READY_TIMEOUT):
            if server_manager.port:
                log_manager.log("SUCCESS", f"✅ 後端服務已就緒，正在啟動代理通道...")
                tunnel_manager = TunnelManager(log_manager=log_manager, stats_dict=shared_stats, port=server_manager.port)
                tunnel_manager.start()
            else:
                log_manager.log("CRITICAL", "伺服器已就緒，但未能解析出埠號。")
        else:
            raise SystemExit(f"伺服器啟動超時 ({SERVER_READY_TIMEOUT}秒)")

        while server_manager._thread.is_alive(): time.sleep(1)

    except (KeyboardInterrupt, SystemExit) as e:
        if log_manager: log_manager.log("WARN", f"🛑 系統正在關閉... 原因: {type(e).__name__}")
    except Exception as e:
        if log_manager: log_manager.log("CRITICAL", f"❌ 發生未預期的致命錯誤: {e}")
    finally:
        if display_manager: display_manager.stop()
        if tunnel_manager: tunnel_manager.stop()
        if server_manager: server_manager.stop()
        end_time = datetime.now(pytz.timezone(TIMEZONE))
        if log_manager and display_manager:
            clear_output(); print("\n".join(display_manager._build_output_buffer()))
            print("\n--- ✅ 所有任務完成，系統已安全關閉 ---")
            display(HTML(create_log_viewer_html(log_manager, display_manager)))
            archive_reports(log_manager, start_time, end_time, shared_stats.get('status', '未知'))

if __name__ == "__main__":
    main()
