# -*- coding: utf-8 -*-
"""
一個輕量級的依賴檢查工具，用於在安裝前確定哪些套件是真正缺失的。
"""

import importlib
import sys
import pkg_resources

# 套件安裝名與導入名之間的對應關係
# 有些套件的安裝名稱與在 Python 中導入時使用的名稱不同。
# 例如，我們用 `pip install Pillow`，但在程式碼中寫 `import PIL`。
PACKAGE_TO_MODULE_MAP = {
    "Pillow": "PIL",
    "python-dotenv": "dotenv",
    "PyYAML": "yaml",
    "websocket-client": "websocket",
    "opencc-python-reimplemented": "opencc",
    "faster-whisper": "faster_whisper",
    "yt-dlp": "yt_dlp",
    "scikit-learn": "sklearn",
    "google-generativeai": "google.generativeai",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "python-multipart": "multipart",
    "psutil": "psutil",
    "requests": "requests",
    "pydub": "pydub",
}

def check_dependency(package_name: str) -> bool:
    """
    檢查單一套件是否可以被成功導入。

    Args:
        package_name: 從 requirements 文件中讀取的套件名稱。

    Returns:
        如果套件已安裝且可導入，則為 True，否則為 False。
    """
    # 移除版本號、註解和附加選項 (如 [standard])
    package_name_base = package_name.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()

    module_name = PACKAGE_TO_MODULE_MAP.get(package_name_base, package_name_base)

    try:
        importlib.import_module(module_name)
        # 對於 uvicorn，我們需要確保 standard 依賴也存在
        if package_name_base == "uvicorn" and "[standard]" in package_name:
             # 檢查 uvloop 是否存在，它是 [standard] 的一個關鍵部分
            importlib.import_module("uvloop")
        return True
    except ImportError:
        return False

def main():
    """
    主函數，從命令列參數讀取 requirements 檔案路徑，
    檢查依賴，並印出缺失的套件。
    """
    if len(sys.argv) < 2:
        print("用法: python check_deps.py <requirements_file_1> [<requirements_file_2> ...]", file=sys.stderr)
        sys.exit(1)

    missing_packages = []
    all_packages = []

    for filepath in sys.argv[1:]:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        all_packages.append(line)
        except FileNotFoundError:
            print(f"錯誤: 找不到檔案 {filepath}", file=sys.stderr)
            continue

    for pkg in all_packages:
        if not check_dependency(pkg):
            missing_packages.append(pkg)

    # 輸出結果
    for pkg in missing_packages:
        print(pkg)

def ensure_dependencies(requirement_files: list[str]):
    """
    一個可重用的函式，確保指定的依賴檔案中的所有套件都已安裝。
    如果偵測到缺失的套件，它會自動呼叫 pip 進行安裝。
    主要設計給其他工具腳本在執行前呼叫，以實現依賴的懶加載。
    """
    import subprocess

    # 將日誌訊息輸出到 stderr，以避免污染 stdout
    print("--- [依賴懶加載] 正在檢查必要套件... ---", file=sys.stderr)

    missing_packages = []
    all_packages = []

    for filepath in requirement_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        all_packages.append(line)
        except FileNotFoundError:
            print(f"錯誤: 懶加載依賴時找不到檔案 {filepath}", file=sys.stderr)
            # 如果找不到依賴檔案，這是一個嚴重問題，直接拋出錯誤
            raise

    for pkg in all_packages:
        if not check_dependency(pkg):
            missing_packages.append(pkg)

    if not missing_packages:
        print("--- [依賴懶加載] 所有套件均已滿足。 ---", file=sys.stderr)
        return

    print(f"--- [依賴懶加載] 偵測到 {len(missing_packages)} 個缺失的套件，正在為您安裝... ---", file=sys.stderr)

    try:
        # 優先嘗試使用 uv 加速器
        pip_command = [sys.executable, "-m", "uv", "pip", "install"] + missing_packages
        print(f"--- [依賴懶加載] 正在嘗試使用 'uv' 快速安裝... ---", file=sys.stderr)
        subprocess.run(pip_command, check=True, capture_output=True, text=True, encoding='utf-8')
        print(f"--- [依賴懶加載] 'uv' 安裝成功。---", file=sys.stderr)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(f"--- [依賴懶加載] 'uv' 不可用或安裝失敗，退回使用 'pip'... ---", file=sys.stderr)
        pip_command = [sys.executable, "-m", "pip", "install"] + missing_packages
        subprocess.run(pip_command, check=True, capture_output=True, text=True, encoding='utf-8')

    print(f"--- [依賴懶加載] 套件安裝完成。 ---", file=sys.stderr)
    # 安裝後，需要讓 Python 的 import 快取失效，以便能找到新安裝的套件
    importlib.invalidate_caches()


if __name__ == "__main__":
    main()
