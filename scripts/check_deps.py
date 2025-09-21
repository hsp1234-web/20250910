# -*- coding: utf-8 -*-
"""
一個輕量級的依賴檢查工具，用於在安裝前確定哪些套件是真正缺失的。
"""

import subprocess
import sys
import os

# 對應 pip install 名稱到 python -m 名稱的特殊案例
MODULE_EXEC_MAP = {
    "yt-dlp": "yt_dlp",
    "Pillow": "PIL",
    "PyYAML": "yaml",
    # 大多數套件的 pip 名稱和模組名稱一致
}

def check_dependency(package_name: str) -> bool:
    """
    終極檢查方法：透過子程序自我執行來驗證套件是否真正可用。
    例如，執行 `python -m yt_dlp --version`。
    這可以完全避免環境分裂和幽靈檔案夾問題。

    Args:
        package_name: 從 requirements 文件中讀取的套件名稱。

    Returns:
        如果套件可執行，則為 True，否則為 False。
    """
    package_name_base = package_name.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()

    # 有些套件無法透過 --version 檢查，我們為它們設定一個後備的檢查命令
    # 對於大多數套件，我們假設它們可以被 import
    module_name = MODULE_EXEC_MAP.get(package_name_base, package_name_base.replace('-', '_'))

    # 預設檢查命令
    command = [sys.executable, "-c", f"import {module_name}"]

    # 為有 --version 的關鍵套件設定更嚴格的檢查
    if package_name_base == "yt-dlp":
        command = [sys.executable, "-m", "yt_dlp", "--version"]
    elif package_name_base == "gdown":
        command = [sys.executable, "-m", "gdown", "--version"]
    elif package_name_base == "faster-whisper":
        # faster-whisper 沒有 --version，但我們可以檢查它是否能被匯入
        command = [sys.executable, "-c", "import faster_whisper"]


    print(f"  [檢查日誌] 正在用命令 '{" ".join(command)}' 驗證 '{package_name_base}'...", file=sys.stderr)
    try:
        # 使用 subprocess.run 來執行命令
        # 我們將 stdout 和 stderr 都定向到 DEVNULL 來保持日誌乾淨
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"  [檢查日誌] ✅ '{package_name_base}' 驗證成功。", file=sys.stderr)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 如果命令失敗 (返回非零碼) 或找不到檔案 (例如 python 解譯器有問題)
        print(f"  [檢查日誌] ❌ '{package_name_base}' 驗證失敗。", file=sys.stderr)
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

if __name__ == "__main__":
    main()
