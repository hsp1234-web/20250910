# src/core/managers/dependency_manager.py
import logging
import subprocess
import sys
from pathlib import Path
import importlib

# --- 路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent

log = logging.getLogger('dependency_manager')

class DependencyManager:
    """負責檢查與安裝應用程式核心依賴的管理器。"""

    def __init__(self):
        self.checker_script = ROOT_DIR / "scripts" / "check_deps.py"
        if not self.checker_script.is_file():
            log.critical(f"依賴檢查腳本 'check_deps.py' 不存在！")
            raise FileNotFoundError("Dependency checker script not found.")

    def _install(self, req_files: list[Path], log_prefix=""):
        """
        智慧地檢查並只安裝缺失的依賴。
        這是從舊的 orchestrator 移植過來的核心邏輯。
        """
        log.info(f"[{log_prefix}] 開始檢查與安裝依賴...")

        req_file_paths = [str(p.resolve()) for p in req_files if p.is_file()]
        if not req_file_paths:
            log.info(f"[{log_prefix}] 找不到任何有效的依賴檔案。")
            return

        try:
            check_command = [sys.executable, str(self.checker_script.resolve())] + req_file_paths
            result = subprocess.run(check_command, capture_output=True, text=True, encoding='utf-8')

            missing_packages = []
            if result.returncode == 0 and result.stdout.strip():
                missing_packages = result.stdout.strip().splitlines()
            elif result.returncode != 0:
                log.warning(f"[{log_prefix}] 依賴檢查腳本執行失敗，將嘗試安裝所有套件。Stderr: {result.stderr}")
                all_packages = []
                for p in req_files:
                    all_packages.extend(p.read_text(encoding='utf-8').strip().splitlines())
                missing_packages = [line for line in all_packages if line and not line.startswith("#")]

            if not missing_packages:
                log.info(f"✅ [{log_prefix}] 所有依賴均已滿足，無需安裝。")
                return

            log.info(f"[{log_prefix}] 偵測到 {len(missing_packages)} 個缺失的套件，開始安裝...")

            # 優先嘗試使用 uv 加速器
            try:
                pip_command = [sys.executable, "-m", "uv", "pip", "install"] + missing_packages
                subprocess.run(pip_command, check=True, capture_output=True, text=True, encoding='utf-8')
                log.info(f"[{log_prefix}] 使用 'uv' 快速安裝成功。")
            except (subprocess.CalledProcessError, FileNotFoundError):
                log.warning(f"[{log_prefix}] 'uv' 不可用或安裝失敗，退回使用 'pip'...")
                pip_command = [sys.executable, "-m", "pip", "install"] + missing_packages
                subprocess.run(pip_command, check=True, capture_output=True, text=True, encoding='utf-8')

            log.info(f"✅ [{log_prefix}] 依賴安裝完成。")

            importlib.invalidate_caches()

        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            log.critical(f"[{log_prefix}] 依賴安裝失敗！ {e}")
            raise

    def setup_core_dependencies(self):
        """安裝所有必要的核心依賴。"""
        log.info("--- 開始設定核心應用依賴 ---")
        core_reqs = [
            ROOT_DIR / "requirements" / "core.txt",
            ROOT_DIR / "requirements" / "features_core.txt",
        ]
        self._install(core_reqs, log_prefix="核心應用")
        log.info("--- 核心應用依賴設定完成 ---")
