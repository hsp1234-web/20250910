# -*- coding: utf-8 -*-
from openbb import obb

def print_market_data_results(data, description):
    """
    專門用於打印市場數據的函數。
    最終修正版：採用最穩健的邏輯檢查返回結果。
    """
    try:
        # 關鍵修正：直接檢查 `data.results` 的真值(truthiness)，
        # 這種方法對 list 和 DataFrame 同樣有效。
        if data and hasattr(data, 'results') and data.results:
            print(f"\n✅ 成功獲取: {description}")
            results_df = data.to_dataframe()

            if not results_df.empty:
                print("  - 最新數據預覽:")
                # 移除 to_string() 不支援的 'indent' 參數
                print(results_df.tail(3).to_string())
            else:
                print("  - 數據獲取成功，但結果為空。")
        else:
            print(f"\n- 資訊：從 OpenBB 未獲取到 '{description}' 的數據。")
    except Exception as e:
        print(f"\n❌ 處理 '{description}' 數據時發生錯誤: {e}")

def fetch_market_data(obb_client):
    """
    使用 OpenBB 獲取市場行情數據。
    這清晰地展示了 OpenBB 超越 fredapi 的獨特價值。
    """
    print("--- 開始從 OpenBB (yfinance) 獲取市場行情數據 ---")
    try:
        data = obb_client.equity.price.historical(symbol='AAPL', provider='yfinance')
        print_market_data_results(data, "蘋果公司 (AAPL) 股價")
    except Exception as e:
        print(f"\n❌ 獲取市場行情數據時發生嚴重錯誤: {e}")
    finally:
        print("--- 市場行情數據獲取完畢 ---")


if __name__ == "__main__":
    try:
        print("正在使用 OpenBB 獲取其獨有的市場行情數據...")
        fetch_market_data(obb)

    except ImportError:
        print("\n錯誤：OpenBB 函式庫未安裝或找不到。")
    except Exception as e:
        print(f"\n執行腳本時發生未預期的嚴重錯誤: {e}")