# 匯入 yfinance 套件，用於下載股票資料
import yfinance as yf

# 定義要測試的股票代號列表
# 包含了使用者提供的不同格式
tickers_to_test = [
    '00969B.TW',   # AI 模型可能抽取的格式 (台灣證券交易所)
    '00969B.TWO',  # Yahoo 股市網站上顯示的格式 (櫃買中心)
    '00969B'       # 使用者額外要求測試的純代號格式
]

print("開始測試 yfinance 對不同股票代號格式的反應...\n")

# 遍歷列表中的每一個代號
for ticker_symbol in tickers_to_test:
    print(f"--- 正在測試代號: {ticker_symbol} ---")
    try:
        # 建立一個 Ticker 物件
        ticker_obj = yf.Ticker(ticker_symbol)

        # 嘗試下載該股票最近5天的歷史資料
        # 我們只需要少量資料來驗證代號是否有效
        history = ticker_obj.history(period="5d")

        # 檢查是否有下載到資料
        if not history.empty:
            print(f"✅ 成功: 代號 '{ticker_symbol}' 有效，已成功下載資料。")
        else:
            # yfinance 對於無效的代號有時會回傳空的 DataFrame
            print(f"❌ 失敗: 代號 '{ticker_symbol}' 無法下載資料，可能為無效代號或已下市。")

    except Exception as e:
        # 如果 yfinance 在過程中拋出任何異常，我們將其捕捉並印出
        print(f"❌ 錯誤: 測試代號 '{ticker_symbol}' 時發生例外狀況: {e}")

    print("-" * (len(ticker_symbol) + 20) + "\n")

print("所有測試已完成。")
