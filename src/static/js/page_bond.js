// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("債券分析儀表板腳本已載入 (v3 - 宣告式觸發)。");

    // --- DOM 元素 ---
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const generateBtn = document.getElementById('btn-generate-report');
    const statusDiv = document.getElementById('update-status');
    const chartsContainer = document.getElementById('charts-container');

    // --- 初始化 ---
    function initialize() {
        // 設定預設日期 (例如，過去一年)
        const today = new Date();
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(today.getFullYear() - 1);

        endDateInput.value = today.toISOString().split('T')[0];
        startDateInput.value = oneYearAgo.toISOString().split('T')[0];

        // 綁定事件
        generateBtn.addEventListener('click', handleGenerateReport);
    }

    // --- 主要邏輯 ---
    async function handleGenerateReport() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;

        if (!startDate || !endDate) {
            updateStatus("請選擇開始和結束日期。", true);
            return;
        }

        // --- 步驟 1: 禁用按鈕並顯示載入狀態 ---
        setLoadingState(true, "步驟 1/3: 正在請求後端更新資料，此過程可能需要一些時間...");
        chartsContainer.innerHTML = ''; // 清空舊圖表

        try {
            // --- 步驟 2: 觸發後端資料更新 (POST 請求) ---
            const triggerResponse = await fetch('/api/bond_service/trigger_update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ start_date: startDate, end_date: endDate })
            });

            if (!triggerResponse.ok) {
                const errorData = await triggerResponse.json();
                throw new Error(`後端資料更新失敗: ${errorData.detail || triggerResponse.statusText}`);
            }

            updateStatus("步驟 2/3: 後端資料已更新，正在抓取圖表數據...");

            // --- 步驟 3: 獲取儀表板數據 (GET 請求) ---
            const dataResponse = await fetch(`/api/bond_service/dashboard_data?start_date=${startDate}&end_date=${endDate}`);

            if (!dataResponse.ok) {
                throw new Error("無法獲取儀表板數據。");
            }

            const data = await dataResponse.json();

            if (data.length === 0) {
                updateStatus("成功，但在選定範圍內無可用數據可供顯示。", false);
            } else {
                updateStatus("步驟 3/3: 數據獲取成功，正在渲染圖表...", false);
                renderCharts(data); // 假設我們將實現一個渲染函式
                updateStatus("✅ 報告已成功生成！", false);
            }

        } catch (error) {
            console.error("生成報告時發生錯誤:", error);
            updateStatus(`❌ 發生錯誤: ${error.message}`, true);
        } finally {
            // --- 步驟 4: 重設 UI 狀態 ---
            setLoadingState(false);
        }
    }

    // --- UI輔助函式 ---
    function setLoadingState(isLoading, message = "") {
        generateBtn.disabled = isLoading;
        if (isLoading) {
            statusDiv.className = 'status-loading';
            statusDiv.textContent = message;
        }
    }

    function updateStatus(message, isError = false) {
        statusDiv.textContent = message;
        statusDiv.className = isError ? 'status-error' : 'status-success';
    }

    // --- 渲染邏輯 (簡易版) ---
    // 在真實應用中，這裡會使用像 Chart.js 或 D3.js 這樣的函式庫
    // 為了簡單起見，我們只顯示數據摘要
    function renderCharts(data) {
        chartsContainer.innerHTML = ''; // 再次清空以防萬一

        // 我們可以定義想要顯示的關鍵指標
        const keyMetrics = {
            'dealer_stress_index': '交易商壓力指數',
            'vix': 'VIX 波動率指數',
            'spread_10y2y': '10年期與2年期公債利差',
            'us_high_yield_spread': '美國高收益債券利差',
            'dealer_net_positions': '交易商淨部位'
        };

        for (const [metric, title] of Object.entries(keyMetrics)) {
            const latestDataPoint = data[data.length - 1];
            if (latestDataPoint && latestDataPoint[metric] !== null) {
                const panel = document.createElement('div');
                panel.className = 'panel';

                const chartTitle = document.createElement('h2');
                chartTitle.textContent = title;

                const valueDisplay = document.createElement('p');
                valueDisplay.style.fontSize = '2em';
                valueDisplay.textContent = parseFloat(latestDataPoint[metric]).toFixed(2);

                const dateDisplay = document.createElement('p');
                dateDisplay.textContent = `最新日期: ${latestDataPoint.date}`;

                panel.appendChild(chartTitle);
                panel.appendChild(valueDisplay);
                panel.appendChild(dateDisplay);

                chartsContainer.appendChild(panel);
            }
        }
    }

    // --- 啟動應用 ---
    initialize();
});
