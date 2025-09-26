// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("一級交易商分析頁面腳本已載入 (v2.0)。");

    // --- DOM 元素獲取 ---
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');

    // --- 指標定義 ---
    const indicators = [
        "sofr", "ofr_fci", "vix", "us_bond_2y_10y_spread",
        "us_high_yield_spread", "stress_index", "dealer_net_positions",
        "dealer_long_term_positions", "dealer_short_term_positions",
        "dealer_net_position_ranking", "dealer_position_change_ranking", "stress_index_macd"
    ];

    /**
     * 設定日期選擇器的預設值。
     * 開始日期固定為 2020-01-01，結束日期為今天。
     */
    function setDefaultDates() {
        const today = new Date();
        const endDate = today.toISOString().split('T')[0]; // 格式: YYYY-MM-DD

        endDateInput.value = endDate;
        startDateInput.value = '2020-01-01';
        console.log(`預設日期已設定: 2020-01-01 至 ${endDate}`);
    }

    /**
     * 根據給定的指標 ID、開始和結束日期載入單個圖表。
     * @param {string} indicatorId - 圖表的指標 ID。
     * @param {string} startDate - 開始日期 (YYYY-MM-DD)。
     * @param {string} endDate - 結束日期 (YYYY-MM-DD)。
     */
    function loadChart(indicatorId, startDate, endDate) {
        const imgElement = document.getElementById(`chart-img-${indicatorId}`);
        if (!imgElement) {
            console.error(`找不到指標 ID 為 ${indicatorId} 的圖片元素。`);
            return;
        }

        console.log(`正在為 ${indicatorId} 載入圖表，日期範圍: ${startDate} 至 ${endDate}`);
        // 顯示載入中的提示
        imgElement.alt = "圖表載入中...";
        // 可以設定一個載入中的預設圖片
        // imgElement.src = "/static/images/loading.gif";

        // 建立 API 端點 URL，並附加日期參數
        let apiUrl = `/api/bond_service/chart/${indicatorId}?start_date=${startDate}&end_date=${endDate}`;
        // 附加時間戳以避免瀏覽器快取舊圖片
        const finalUrl = `${apiUrl}&t=${new Date().getTime()}`;

        // 設定圖片載入成功和失敗的事件處理
        imgElement.onload = () => {
            console.log(`${indicatorId} 圖表載入成功。`);
            imgElement.alt = `指標 ${indicatorId} 的圖表`;
        };

        imgElement.onerror = () => {
            console.error(`${indicatorId} 圖表載入失敗。`);
            imgElement.alt = "圖表載入失敗，請檢查後端服務。";
            // 可以在此處顯示一個預設的錯誤圖片
            // imgElement.src = "/static/images/error.png";
        };

        // 開始非同步載入圖片
        imgElement.src = finalUrl;
    }

    /**
     * 讀取日期選擇器的值，並載入所有圖表。
     */
    function loadAllCharts() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;

        if (!startDate || !endDate) {
            alert('請選擇有效的開始與結束日期。');
            return;
        }

        if (new Date(startDate) > new Date(endDate)) {
            alert('開始日期不能晚於結束日期。');
            return;
        }

        console.log(`準備更新所有圖表，日期範圍: ${startDate} 至 ${endDate}`);

        indicators.forEach(indicatorId => {
            loadChart(indicatorId, startDate, endDate);
        });
    }

    // --- 初始化流程 ---

    // 1. 設定預設日期
    setDefaultDates();

    // 2. 頁面首次載入時，使用預設日期載入所有圖表
    loadAllCharts();

    // 3. 為更新按鈕綁定事件監聽器
    if (updateBtn) {
        updateBtn.addEventListener('click', loadAllCharts);
    } else {
        console.error("找不到 ID 為 'update-charts-btn' 的按鈕。");
    }
});