# -*- coding: utf-8 -*-

def print_openbb_results(data, description):
    """
    通用函數，用於打印 OpenBB 回傳的結果。
    """
    try:
        if data and hasattr(data, 'results') and data.results:
            print(f"\n成功獲取: {description}")
            results = data.results

            if isinstance(results, list):
                print("  - 最新數據預覽 (List):")
                for item in results[-3:]:
                    print(f"    {item}")
            else:
                print("  - 最新數據預覽 (DataFrame):")
                print(results.tail(3).to_string(indent="    "))
        else:
            print(f"\n從 OpenBB 未獲取到 '{description}' 的有效數據或返回結果為空。")
    except Exception as e:
        print(f"\n處理 '{description}' 數據時發生錯誤: {e}")


def fetch_treasury_rates(obb):
    """使用 OpenBB SDK 獲取美國公債殖利率曲線。"""
    print("--- (1/2) 開始從 OpenBB 獲取公債殖利率曲線 ---")
    try:
        data = obb.fixedincome.government.treasury_rates()
        print_openbb_results(data, "美國公債殖利率曲線")
    except Exception as e:
        print(f"\n獲取公債殖利率曲線時發生錯誤: {e}")
    print("\n--- 公債殖利率曲線獲取完畢 ---")

def fetch_macroeconomic_data(obb):
    """使用 OpenBB SDK 獲取核心總體經濟指標。"""
    print("\n--- (2/2) 開始從 OpenBB 獲取總體經濟指標 ---")

    # 最終修正：使用 FRED Series ID 作為 symbol
    indicators_to_fetch = {
        "失業率 (UNRATE)": lambda: obb.economy.unemployment(),
        "消費者物價指數 (CPIAUCSL)": lambda: obb.economy.indicators(symbol='CPIAUCSL', country='united_states'),
        "實質國內生產毛額 (GDPC1)": lambda: obb.economy.indicators(symbol='GDPC1', country='united_states'),
        "生產者物價指數 (PPIACO)": lambda: obb.economy.indicators(symbol='PPIACO', country='united_states'),
        "密西根大學消費者信心指數 (UMCSENT)": lambda: obb.economy.survey.university_of_michigan()
    }

    for description, command in indicators_to_fetch.items():
        try:
            data = command()
            print_openbb_results(data, description)
        except Exception as e:
            print(f"\n獲取 '{description}' 時發生錯誤: {e}")

    print("\n--- 總體經濟指標獲取完畢 ---")


if __name__ == "__main__":
    try:
        from openbb import obb

        # 在執行任何操作前，以程式碼設定 FRED API 金鑰
        print("正在設定 OpenBB 的 FRED API 金鑰...")
        obb.user.credentials.fred_api_key = "52c28a554a935b05215682b7910623a3"
        print("API 金鑰設定完畢。")

        fetch_treasury_rates(obb)
        fetch_macroeconomic_data(obb)
    except ImportError:
        print("\n錯誤：OpenBB 函式庫未安裝或找不到。")
    except Exception as e:
        print(f"執行腳本時發生未預期的錯誤: {e}")