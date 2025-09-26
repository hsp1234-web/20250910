// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("一級交易商分析頁面腳本已載入。");

    // --- DOM 元素 ---
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');

    // --- 指標清單 ---
    const indicators = [
        "sofr", "ofr_fci", "vix", "us_bond_2y_10y_spread",
        "us_high_yield_spread", "stress_index", "dealer_net_positions",
        "dealer_long_term_positions", "dealer_short_term_positions",
        "dealer_net_position_ranking", "dealer_position_change_ranking", "stress_index_macd"
    ];

    // --- 函式定義 ---

    /**
     * 載入所有圖表。會讀取當前日期選擇器的值。
     */
    function loadAllCharts() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;

        if (!startDate || !endDate) {
            alert("請確保已選擇開始和結束日期。");
            return;
        }

        console.log(`開始載入所有圖表，日期範圍: ${startDate} 至 ${endDate}`);

        // 為每個圖表容器顯示 loading 提示
        indicators.forEach(id => {
            const imgElement = document.getElementById(`chart-img-${id}`);
            if (imgElement) {
                imgElement.src = ""; // 清空舊圖片
                imgElement.alt = "圖表載入中...";
            }
        });

        // 遍歷所有指標並非同步載入圖表
        indicators.forEach(indicatorId => {
            loadChart(indicatorId, startDate, endDate);
        });
    }

    /**
     * 根據指標 ID 和日期範圍載入單一圖表。
     * @param {string} indicatorId - 指標的唯一 ID。
     * @param {string} startDate - 開始日期 (YYYY-MM-DD)。
     * @param {string} endDate - 結束日期 (YYYY-MM-DD)。
     */
    function loadChart(indicatorId, startDate, endDate) {
        const imgElement = document.getElementById(`chart-img-${indicatorId}`);
        if (!imgElement) {
            console.error(`找不到指標 ID 為 ${indicatorId} 的圖片元素。`);
            return;
        }

        // 建立 API 端點 URL，並附加日期參數
        let apiUrl = `/api/bond_service/chart/${indicatorId}?start_date=${startDate}&end_date=${endDate}`;
        // 附加時間戳以避免瀏覽器快取舊圖片
        const finalUrl = `${apiUrl}&t=${new Date().getTime()}`;

        imgElement.onload = () => {
            console.log(`${indicatorId} 圖表載入成功。`);
            imgElement.alt = `指標 ${indicatorId} 的圖表`;
        };

        imgElement.onerror = () => {
            console.error(`${indicatorId} 圖表載入失敗。`);
            imgElement.alt = "圖表載入失敗，請檢查後端服務或日期範圍。";
        };

        // 開始非同步載入圖片
        imgElement.src = finalUrl;
    }

    /**
     * 設定預設日期範圍。
     */
    function setDefaultDates() {
        const today = new Date();
        const endDate = today.toISOString().split('T')[0];

        // 預設開始日期為 2020-01-01
        const startDate = "2020-01-01";

        startDateInput.value = startDate;
        endDateInput.value = endDate;
        console.log(`已設定預設日期範圍: ${startDate} 至 ${endDate}`);
    }

    // --- 初始化與事件綁定 ---

    // 1. 為更新按鈕綁定點擊事件
    if (updateBtn) {
        updateBtn.addEventListener('click', loadAllCharts);
    } else {
        console.error("找不到更新按鈕元素。");
    }

    // 2. 設定預設日期並在頁面首次載入時獲取圖表
    setDefaultDates();
    loadAllCharts();
});