// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("一級交易商分析頁面腳本已載入。");

    // --- DOM 元素 ---
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');

    // --- 指標清單 ---
    // 將 "stress_index_macd" 移除，因為它現在是動態載入的
    const indicators = [
        "sofr", "ofr_fci", "vix", "us_bond_2y_10y_spread",
        "us_high_yield_spread", "stress_index", "dealer_net_positions",
        "dealer_long_term_positions", "dealer_short_term_positions",
        "dealer_net_position_ranking", "dealer_position_change_ranking"
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

    /**
     * 初始化動態圖表，包括獲取初始數據和設定 SSE 連線。
     */
    async function initializeDynamicChart() {
        const chartContainer = document.getElementById('dynamic-chart-stress-index-macd');
        if (!chartContainer) {
            console.error("找不到動態圖表的容器。");
            return;
        }

        try {
            // 1. 獲取初始圖表數據
            console.log("正在獲取壓力指數圖表的初始數據...");
            const response = await fetch('/api/bond_service/charts/stress-index');
            if (!response.ok) {
                throw new Error(`獲取初始數據失敗: ${response.statusText}`);
            }
            const data = await response.json();
            console.log(`成功獲取 ${data.length} 筆初始數據。`);

            if (data.length === 0) {
                chartContainer.innerHTML = '<div class="placeholder">無可用數據來繪製圖表。</div>';
                return;
            }

            // 處理數據以適應 Plotly
            const dates = data.map(d => d.date);
            const stressIndex = data.map(d => d.dealer_stress_index);
            const macdLine = data.map(d => d.macd_line);
            const macdSignalLine = data.map(d => d.macd_signal_line);
            const macdHist = data.map(d => d.macd_hist);

            // 2. 使用 Plotly.js 繪製初始圖表
            const plotData = [
                {
                    x: dates,
                    y: stressIndex,
                    type: 'scatter',
                    mode: 'lines',
                    name: '壓力指數',
                    yaxis: 'y1'
                },
                {
                    x: dates,
                    y: macdLine,
                    type: 'scatter',
                    mode: 'lines',
                    name: 'MACD 線',
                    yaxis: 'y2'
                },
                {
                    x: dates,
                    y: macdSignalLine,
                    type: 'scatter',
                    mode: 'lines',
                    name: '訊號線',
                    yaxis: 'y2'
                },
                {
                    x: dates,
                    y: macdHist,
                    type: 'bar',
                    name: 'MACD 柱',
                    yaxis: 'y2',
                    marker: {
                        color: macdHist.map(v => v >= 0 ? 'rgba(255, 0, 0, 0.6)' : 'rgba(0, 128, 0, 0.6)')
                    }
                }
            ];

            const layout = {
                title: '壓力指數與 MACD (即時更新)',
                xaxis: { title: '日期' },
                yaxis: { title: '壓力指數', side: 'left' },
                yaxis2: {
                    title: 'MACD',
                    overlaying: 'y',
                    side: 'right',
                    showgrid: false
                },
                legend: { x: 0, y: 1.15, orientation: 'h' },
                margin: { l: 50, r: 50, t: 80, b: 50 }
            };

            Plotly.newPlot(chartContainer, plotData, layout, {responsive: true});
            console.log("動態圖表已成功初始化。");

            // 3. 設定 Server-Sent Events (SSE) 以接收即時更新
            connectToSSE();

        } catch (error) {
            console.error("初始化動態圖表時發生錯誤:", error);
            chartContainer.innerHTML = `<div class="placeholder">圖表載入失敗: ${error.message}</div>`;
        }
    }

    /**
     * 連接到 SSE 端點並設定事件監聽器。
     */
    function connectToSSE() {
        console.log("正在連接到 SSE 端點以接收即時更新...");
        const eventSource = new EventSource('/api/bond_service/charts/stream-updates');

        eventSource.onmessage = function(event) {
            const newData = JSON.parse(event.data);
            console.log("收到 SSE 更新:", newData);

            // 使用 Plotly.extendTraces 來新增數據點
            Plotly.extendTraces('dynamic-chart-stress-index-macd', {
                x: [[newData.date], [newData.date], [newData.date], [newData.date]],
                y: [
                    [newData.dealer_stress_index],
                    [newData.macd_line],
                    [newData.macd_signal_line],
                    [newData.macd_hist]
                ]
            }, [0, 1, 2, 3]); // 對應到 plotData 中的四個軌跡
        };

        eventSource.onerror = function(error) {
            console.error("SSE 連線發生錯誤，將在 10 秒後嘗試重新連接:", error);
            eventSource.close();
            // 關鍵修正：使用 setTimeout 來安排重連，而不是直接遞迴呼叫，以避免堆疊溢位。
            setTimeout(connectToSSE, 10000);
        };
    }

    // 3. 初始化動態圖表
    initializeDynamicChart();
});