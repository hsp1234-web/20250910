# -*- coding: utf-8 -*-
import sys
import os
import argparse
from pathlib import Path
import importlib.util

if not hasattr(importlib, 'abc'):
    spec = importlib.util.find_spec('importlib.abc')
    if spec:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        setattr(importlib, 'abc', module)
        sys.modules['importlib.abc'] = module

try:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    SRC_DIR = ROOT_DIR / "src"
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    if str(SRC_DIR) not in sys.path:
        sys.path.insert(0, str(SRC_DIR))

    from google.colab import userdata
    from src.core import key_manager
    from src.db import database
    print("✅ 成功匯入 Colab userdata, key_manager, 和 database 模組。")
except ImportError:
    print("❌ 錯誤：此腳本似乎並非在 Google Colab 環境中執行，或專案結構不完整。")
    class MockUserdata:
        def get(self, key): return os.environ.get(key)
        def get_all(self): return os.environ
    userdata = MockUserdata()
    from src.core import key_manager
    from src.db import database
    print("⚠️ 警告：未在 Colab 環境中，將從 OS 環境變數讀取金鑰。")
except Exception as e:
    print(f"❌ 載入模組時發生未預期的錯誤: {e}")
    sys.exit(1)

def main():
    conn = None
    try:
        conn = database.get_db_connection()
        if not conn:
            raise ConnectionError("無法建立資料庫連線。")

        with conn:
            print("🧹 正在清除所有舊的金鑰記錄...")
            cleared_count = key_manager.clear_all_keys(conn)
            print(f"✅ 成功清除了 {cleared_count} 筆舊記錄。")

        parser = argparse.ArgumentParser(description="Colab 金鑰注入器，支援自動與手動模式。")
        parser.add_argument("--mode", type=str, choices=['auto', 'manual'], required=True, help="金鑰載入模式：'auto' 或 'manual'")
        parser.add_argument("--count", type=int, default=0, help="在自動模式下，要載入的金鑰數量 (0-20)。")
        parser.add_argument("--manual-keys", type=str, default="", help="在手動模式下，包含金鑰的字串（以換行符分隔）。")
        parser.add_argument("--fred-key", type=str, default="", help="用於傳遞 FRED API 金鑰。")
        args = parser.parse_args()

        print("\n" + "="*50)
        print("🔑 開始從所有指定來源收集金鑰...")
        keys_to_add = []
        if args.mode == 'auto':
            print("   - 模式：自動 | 正在從 Colab Secrets 讀取 Gemini 金鑰...")
            base_key_name = "GOOGLE_API_KEY"
            target_key_names = [base_key_name]
            if args.count > 0:
                target_key_names.extend([f"{base_key_name}_{i}" for i in range(1, args.count + 1)])
            for key_name in target_key_names:
                try:
                    key_value = userdata.get(key_name)
                    if key_value and key_value.strip():
                        keys_to_add.append({"value": key_value, "name": key_name, "type": "gemini"})
                        print(f"     > 找到金鑰: {key_name}")
                except Exception:
                    print(f"     > 未找到或讀取 '{key_name}' 失敗，跳過。")
        elif args.mode == 'manual':
            print("   - 模式：手動 | 正在解析貼上的 Gemini 金鑰...")
            raw_keys = [key.strip() for key in args.manual_keys.split('\n') if key.strip()]
            for i, key_value in enumerate(raw_keys):
                key_name = f"Manual-Key-{i+1}"
                keys_to_add.append({"value": key_value, "name": key_name, "type": "gemini"})
                print(f"     > 找到第 {i+1} 把手動金鑰")

        print("   - 正在從命令列參數讀取 FRED 金鑰...")
        if args.fred_key and args.fred_key.strip():
            keys_to_add.append({"value": args.fred_key, "name": "FRED 金鑰 (自動載入)", "type": "fred"})
            print("     > 找到 FRED 金鑰。")
        else:
            print("     > 未找到 FRED 金鑰。")
        print(f"🔑 金鑰收集完畢，共找到 {len(keys_to_add)} 個金鑰準備注入。")
        print("="*50)

        if not keys_to_add:
            print("\n🟡 未找到任何金鑰，無需注入。")
            return

        with conn:
            print("\n🚀 開始將金鑰注入資料庫...")
            added_count = 0
            for key_info in keys_to_add:
                try:
                    key_manager.add_key(conn, key_value=key_info["value"], key_name=key_info["name"], key_type=key_info["type"], validate=False)
                    print(f"   - ✅ 成功注入金鑰: '{key_info['name']}' (類型: {key_info['type']})")
                    added_count += 1
                except ValueError as e:
                    print(f"   - 🟡 跳過金鑰 '{key_info['name']}'：{e}")
                except Exception as e:
                    print(f"   - 💥 處理金鑰 '{key_info['name']}' 時發生未預期錯誤：{e}")
        print("\n" + "="*50)
        print(f"🏁 金鑰注入流程結束！成功注入 {added_count} 個新金鑰。")
        print("="*50 + "\n")

    except Exception as e:
        print(f"\n💥 在執行過程中發生嚴重錯誤: {e}")
        print("請檢查您的 Colab 環境權限或祕密設定。")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    main()
