// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("一級交易商分析頁面腳本已載入。");

    // 定義所有圖表的指標 ID
    const indicators = [
        "sofr",
        "ofr_fci",
        "vix",
        "us_bond_2y_10y_spread",
        "us_high_yield_spread",
        "stress_index",
        "dealer_net_positions",
        "dealer_long_term_positions",
        "dealer_short_term_positions",
        "dealer_net_position_ranking",
        "dealer_position_change_ranking",
        "stress_index_macd"
    ];

    // 遍歷所有指標並非同步載入圖表
    indicators.forEach(indicatorId => {
        loadChart(indicatorId);
    });

    function loadChart(indicatorId) {
        const imgElement = document.getElementById(`chart-img-${indicatorId}`);
        if (!imgElement) {
            console.error(`找不到指標 ID 為 ${indicatorId} 的圖片元素。`);
            return;
        }

        console.log(`正在為 ${indicatorId} 載入圖表...`);

        // 建立 API 端點 URL，指向主機的代理服務
        const apiUrl = `/api/bond_service/chart/${indicatorId}`;
        // 附加時間戳以避免瀏覽器快取舊圖片
        const finalUrl = `${apiUrl}?t=${new Date().getTime()}`;

        // 設定圖片載入成功和失敗的事件處理
        imgElement.onload = () => {
            console.log(`${indicatorId} 圖表載入成功。`);
            // 成功載入後，可以移除或更改 alt 文字
            imgElement.alt = `指標 ${indicatorId} 的圖表`;
        };

        imgElement.onerror = () => {
            console.error(`${indicatorId} 圖表載入失敗。`);
            // 顯示錯誤訊息
            imgElement.alt = "圖表載入失敗，請檢查後端服務。";
            // 可以在此處顯示一個預設的錯誤圖片
            // imgElement.src = "/static/images/error.png";
        };

        // 開始非同步載入圖片
        imgElement.src = finalUrl;
    }
});