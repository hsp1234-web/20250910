# -*- coding: utf-8 -*-
"""
此腳本專為在 Google Colab 環境中啟動時執行而設計。

它的功能是根據從 colabPro.py 傳入的命令列參數，
以兩種不同模式將 API 金鑰注入系統：

1.  **自動模式 (`auto`)**:
    - 從 Colab 的祕密管理器 (Secrets) 中讀取 `GOOGLE_API_KEY...` 系列金鑰。
    - 讀取的數量由 `--count` 參數控制。

2.  **手動模式 (`manual`)**:
    - 直接解析由 `--manual-keys` 參數傳入的金鑰字串（以換行符分隔）。

此腳本會呼叫核心的 key_manager 來安全地新增、驗證和儲存金鑰。
"""

import sys
import os
import argparse
from pathlib import Path
import importlib.util

# --- (WORKAROUND) Python 3.10+ Compatibility Shim for 'importlib.abc' ---
# 在 Python 3.10+ 中, 'importlib.abc' 被移出頂層 'importlib' 模組.
# 此補丁手動將其加回, 以支援可能使用舊路徑的較舊依賴項。
if not hasattr(importlib, 'abc'):
    spec = importlib.util.find_spec('importlib.abc')
    if spec:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        setattr(importlib, 'abc', module)
        sys.modules['importlib.abc'] = module
# --- End of WORKAROUND ---

# --- 路徑設定，確保可以正確匯入專案模組 ---
try:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    SRC_DIR = ROOT_DIR / "src"
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from google.colab import userdata
    from src.core import key_manager
    print("✅ 成功匯入 Colab userdata 和 key_manager 模組。")
except ImportError:
    print("❌ 錯誤：此腳本似乎並非在 Google Colab 環境中執行，或專案結構不完整。")
    # 在非 Colab 環境下，建立一個模擬的 userdata 物件以便本機測試
    class MockUserdata:
        def get(self, key): return os.environ.get(key)
        def get_all(self): return os.environ
    userdata = MockUserdata()
    from src.core import key_manager
    print("⚠️ 警告：未在 Colab 環境中，將從 OS 環境變數讀取金鑰。")
except Exception as e:
    print(f"❌ 載入模組時發生未預期的錯誤: {e}")
    sys.exit(1)


def handle_auto_mode(count: int):
    """處理自動模式：從 Colab Secrets 讀取金鑰。"""
    print("\n" + "="*50)
    print(f"🚀 模式：自動 | 嘗試從 Colab Secrets 載入 {count + 1} 組金鑰...")
    print("="*50)

    base_key_name = "GOOGLE_API_KEY"
    target_key_names = [base_key_name]
    if count > 0:
        target_key_names.extend([f"{base_key_name}_{i}" for i in range(1, count + 1)])

    added_count = 0
    for key_name in target_key_names:
        try:
            key_value = userdata.get(key_name)
            if not key_value or not key_value.strip():
                print(f"🟡 未找到名為 '{key_name}' 的金鑰，跳過。")
                continue

            print(f"🔄  正在新增金鑰 '{key_name}' (稍後驗證)...")
            # 解決競爭條件：在啟動時只新增金鑰，不立即驗證。
            # 驗證將由使用者在 UI 介面或 API 觸發，此時依賴已全部安裝。
            key_manager.add_key(key_value, key_name, validate=False)
            print(f"✅  成功新增金鑰 '{key_name}' 至設定檔。")
            added_count += 1

        except ValueError as e:
            print(f"🟡  跳過金鑰 '{key_name}'：{e}")
        except Exception as e:
            print(f"💥  處理金鑰 '{key_name}' 時發生未預期錯誤：{e}")

    print("-" * 50)
    print(f"🏁 自動模式處理完成！成功新增 {added_count} 個新金鑰。")
    print("="*50 + "\n")


def handle_manual_mode(keys_string: str):
    """處理手動模式：解析並新增使用者貼上的金鑰。"""
    print("\n" + "="*50)
    print("🚀 模式：手動 | 正在處理使用者貼上的金鑰...")
    print("="*50)

    keys = [key.strip() for key in keys_string.split('\n') if key.strip()]

    if not keys:
        print("🟡 未提供任何手動輸入的金鑰。")
        print("="*50)
        return

    added_count = 0
    for i, key_value in enumerate(keys):
        key_name = f"Manual-Key-{i+1}"
        print(f"🔄  正在新增第 {i+1} 把手動金鑰 (稍後驗證)...")
        try:
            # 解決競爭條件：在啟動時只新增金鑰，不立即驗證。
            key_manager.add_key(key_value, key_name, validate=False)
            print(f"✅  成功新增金鑰 '{key_name}' 至設定檔。")
            added_count += 1
        except ValueError as e:
            print(f"🟡  跳過第 {i+1} 把手動金鑰：{e}")
        except Exception as e:
            print(f"💥  處理第 {i+1} 把手動金鑰時發生未預期錯誤：{e}")

    print("-" * 50)
    print(f"🏁 手動模式處理完成！成功新增 {added_count} 個新金鑰。")
    print("="*50 + "\n")


def main():
    """主執行函式，解析參數並分派任務。"""
    parser = argparse.ArgumentParser(description="Colab 金鑰注入器，支援自動與手動模式。")
    parser.add_argument("--mode", type=str, choices=['auto', 'manual'], required=True, help="金鑰載入模式：'auto' 或 'manual'")
    parser.add_argument("--count", type=int, default=0, help="在自動模式下，要載入的金鑰數量 (0-20)。")
    parser.add_argument("--manual-keys", type=str, default="", help="在手動模式下，包含金鑰的字串（以換行符分隔）。")

    args = parser.parse_args()

    try:
        if args.mode == 'auto':
            handle_auto_mode(args.count)
        elif args.mode == 'manual':
            handle_manual_mode(args.manual_keys)
    except Exception as e:
        print(f"\n💥 在執行過程中發生嚴重錯誤: {e}")
        print("請檢查您的 Colab 環境權限或祕密設定。")
        sys.exit(1)

if __name__ == "__main__":
    main()
