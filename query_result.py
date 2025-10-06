import sqlite3
import json
from pathlib import Path

# --- 資料庫與測試目標設定 ---
DB_FILE = Path(__file__).parent / "services" / "document_processor_service" / "document_processor.sqlite3"
TEST_URL = "https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing"

def query_and_print_result():
    """連接到資料庫，查詢指定 URL 的分析結果，並以格式化的方式印出。"""
    print("="*60)
    print("      本地模型分析品質評估報告 (模型: gemma2:2b)")
    print("="*60)

    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM processed_documents WHERE source_url = ?", (TEST_URL,))
        result = cursor.fetchone()

        if not result:
            print(f"\n錯誤：在資料庫中找不到 URL '{TEST_URL}' 的分析結果。")
            return

        print("\n--- 1. 模型分析結果 (從資料庫讀取) ---\n")

        # 將查詢結果轉換為字典，並格式化輸出
        result_dict = dict(result)
        # 移除我們不需要在報告中看到的欄位
        result_dict.pop('id', None)
        result_dict.pop('error_message', None)

        # 使用 json.dumps 進行美化輸出
        print(json.dumps(result_dict, indent=2, ensure_ascii=False))

    except sqlite3.Error as e:
        print(f"\n查詢資料庫時發生錯誤: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    query_and_print_result()