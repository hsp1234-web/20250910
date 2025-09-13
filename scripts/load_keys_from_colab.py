# -*- coding: utf-8 -*-
"""
此腳本專為在 Google Colab 環境中執行而設計。

它的主要功能是在應用程式啟動前，自動從 Colab 的祕密管理器 (Secrets)
中讀取所有預先設定的 Gemini API 金鑰，並將它們安全地新增到
應用程式的金鑰池 (`keys.json`) 中。

使用者應在 Colab 的祕密管理器中，將金鑰命名為：
- GEMINI_API_KEY_1
- GEMINI_API_KEY_2
- ...

此腳本會自動偵測所有以此為前綴的祕密並試圖載入。
"""

import sys
import os
from pathlib import Path

# --- 路徑設定，確保可以正確匯入專案模組 ---
# 將專案根目錄加到 sys.path
try:
    # 這個腳本位於 scripts/ 目錄下，所以我們需要往上兩層來到根目錄
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
    print("❌ 錯誤：此腳本必須在 Google Colab 環境中執行，且專案結構需完整。")
    sys.exit(1)
except Exception as e:
    print(f"❌ 載入模組時發生未預期的錯誤: {e}")
    sys.exit(1)

# --- 常數定義 ---
KEY_PREFIX = "GEMINI_API_KEY_"

def main():
    """
    主執行函式。
    """
    print("\n" + "="*50)
    print("🚀 開始從 Colab Secrets 自動載入 API 金鑰...")
    print("="*50)

    try:
        # 獲取所有使用者定義的祕密鍵
        all_secret_keys = userdata.get_all()
        # 篩選出我們感興趣的 API 金鑰
        api_key_names = sorted([key for key in all_secret_keys if key.startswith(KEY_PREFIX)])

        if not api_key_names:
            print(f"🟡 未在 Colab Secrets 中找到任何以 '{KEY_PREFIX}' 為前綴的金鑰。")
            print("如果您想自動載入金鑰，請在 Colab 的「祕密」分頁中新增它們。")
            print("例如：GEMINI_API_KEY_1, GEMINI_API_KEY_2 等。")
            print("="*50)
            sys.exit(0)

        print(f"🔍 找到 {len(api_key_names)} 個潛在的 API 金鑰，將逐一進行驗證與新增...")
        print("-" * 50)

        added_count = 0
        for key_name in api_key_names:
            key_value = userdata.get(key_name)
            if not key_value or not key_value.strip():
                print(f"⚠️  跳過 '{key_name}'：金鑰值為空。")
                continue

            print(f"🔄  正在處理金鑰 '{key_name}'...")
            try:
                # 使用 key_manager 的函式來新增金鑰
                # key_manager.add_key 內部會自動處理驗證、雜湊和儲存
                result = key_manager.add_key(key_value, key_name)
                if result.get("is_valid"):
                    print(f"✅  成功新增並驗證金鑰 '{key_name}'。")
                    added_count += 1
                else:
                    print(f"❌  金鑰 '{key_name}' 新增失敗：未能通過有效性驗證。")
            except ValueError as e:
                # 捕獲 key_manager 可能拋出的錯誤，例如「金鑰已存在」
                print(f"🟡  跳過金鑰 '{key_name}'：{e}")
            except Exception as e:
                print(f"💥  處理金鑰 '{key_name}' 時發生未預期錯誤：{e}")

        print("-" * 50)
        print(f"🏁 處理完成！成功新增 {added_count} 個新金鑰。")
        print("="*50 + "\n")

    except Exception as e:
        print(f"\n💥 在執行過程中發生嚴重錯誤: {e}")
        print("請檢查您的 Colab 環境權限或祕密設定。")
        sys.exit(1)

if __name__ == "__main__":
    main()
