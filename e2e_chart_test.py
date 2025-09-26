# e2e_chart_test.py
import requests
import os
import time

# --- 設定 ---
BASE_URL = "http://127.0.0.1:8000"
CHART_IDS = [
    "sofr",
    "spread_10y2y",
    "move_index",
    "vix",
    "dealer_positions",
    "reserves",
    # "etf_tlt", # 暫時註解掉，因為我們沒有明確加入 ETF 的數據抓取
    "pos_res_ratio",
    "stress_index",
    "macd",
    "gauge",
    "trend",
]
OUTPUT_DIR = "test_charts"

def run_test():
    """執行端對端圖表生成測試"""
    print("--- 開始執行端對端圖表生成測試 ---")

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"已建立輸出目錄: {OUTPUT_DIR}")

    success_count = 0
    failed_charts = []

    # 等待伺服器啟動
    print("等待伺服器啟動 (5秒)...")
    time.sleep(5)

    for chart_id in CHART_IDS:
        url = f"{BASE_URL}/chart/{chart_id}"
        output_path = os.path.join(OUTPUT_DIR, f"{chart_id}.jpeg")

        print(f"\n[測試中] 正在請求圖表: {chart_id}")
        print(f"  -> URL: {url}")

        try:
            response = requests.get(url, timeout=300) # 加長超時時間，因為計算可能耗時

            if response.status_code == 200:
                # 檢查回傳的是否為圖片
                if 'image/jpeg' in response.headers.get('content-type', ''):
                    with open(output_path, 'wb') as f:
                        f.write(response.content)

                    # 檢查檔案是否已生成且非空
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000: # 1KB
                        print(f"✅ [成功] 圖表 '{chart_id}' 已成功生成並儲存至 {output_path}")
                        success_count += 1
                    else:
                        print(f"❌ [失敗] 圖表 '{chart_id}' 儲存後檔案無效 (空檔案或過小)。")
                        failed_charts.append(chart_id)
                else:
                    print(f"❌ [失敗] 圖表 '{chart_id}' 回應成功，但內容不是 JPEG 圖片。Content-Type: {response.headers.get('content-type')}")
                    failed_charts.append(chart_id)
            else:
                print(f"❌ [失敗] 圖表 '{chart_id}' 請求失敗。狀態碼: {response.status_code}")
                print(f"   -> 錯誤訊息: {response.text}")
                failed_charts.append(chart_id)

        except requests.exceptions.RequestException as e:
            print(f"❌ [失敗] 圖表 '{chart_id}' 請求時發生網路錯誤: {e}")
            failed_charts.append(chart_id)

    print("\n--- 測試總結 ---")
    print(f"總計測試圖表數: {len(CHART_IDS)}")
    print(f"成功: {success_count}")
    print(f"失敗: {len(failed_charts)}")
    if failed_charts:
        print(f"失敗的圖表 ID: {', '.join(failed_charts)}")

    print("\n測試執行完畢。請檢查 'test_charts' 目錄下的圖片。")

if __name__ == "__main__":
    run_test()