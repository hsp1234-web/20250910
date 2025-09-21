# -*- coding: utf-8 -*-
"""
一個輕量級的依賴檢查工具，用於在安裝前確定哪些套件是真正缺失的。
"""

import importlib.metadata
import sys
import os

def check_dependency(package_name: str) -> bool:
    """
    使用 importlib.metadata.version 檢查套件是否已完整安裝。
    這是最穩健的方法，無法被空的幽靈資料夾欺騙。

    Args:
        package_name: 從 requirements 文件中讀取的套件名稱。

    Returns:
        如果套件已安裝，則為 True，否則為 False。
    """
    # 移除版本號、註解和附加選項 (如 [standard])
    package_name_base = package_name.split("==")[0].split(">=")[0].split("<=")[0].split("[")[0].strip()

    try:
        # 嘗試獲取套件的版本。如果成功，表示套件已完整安裝。
        version = importlib.metadata.version(package_name_base)
        print(f"  [檢查日誌] 找到了 '{package_name_base}' 版本 {version}", file=sys.stderr)

        # 對於 uvicorn[standard]，還需要額外檢查 uvloop
        if package_name_base == "uvicorn" and "[standard]" in package_name:
            try:
                importlib.metadata.version("uvloop")
                print(f"  [檢查日誌] 找到了 'uvicorn' 的 'uvloop' 依賴", file=sys.stderr)
            except importlib.metadata.PackageNotFoundError:
                print(f"  [檢查日誌] 未找到 'uvicorn' 的 'uvloop' 依賴", file=sys.stderr)
                return False
        return True
    except importlib.metadata.PackageNotFoundError:
        # 如果找不到套件元數據，則視為未安裝。
        print(f"  [檢查日誌] 找不到套件 '{package_name_base}'", file=sys.stderr)
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
