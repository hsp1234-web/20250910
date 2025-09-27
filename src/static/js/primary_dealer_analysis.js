// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("互動式圖表腳本已載入 (v2.0)。");

    // --- 全域變數與設定 ---
    const chartInstances = {}; // 儲存所有 Chart.js 的實例，用於更新和銷毀
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');
    const chartPanels = document.querySelectorAll('.panel[data-indicator-id]');

    // --- 函式定義 ---

    /**
     * 在指定的 Canvas 上渲染或更新圖表。
     * @param {string} indicatorId - 指標 ID，用於獲取 canvas 元素。
     * @param {object} chartData - 從 API 獲取的數據，包含 labels 和 datasets。
     */
    function renderChart(indicatorId, chartData) {
        const canvasId = `chart-canvas-${indicatorId}`;
        const ctx = document.getElementById(canvasId);
        if (!ctx) {
            console.error(`找不到 ID 為 ${canvasId} 的 canvas 元素。`);
            return;
        }

        // 如果已有圖表實例，先銷毀它以避免記憶體洩漏和重疊渲染
        if (chartInstances[indicatorId]) {
            chartInstances[indicatorId].destroy();
        }

        // 預設圖表類型為 'line'
        const chartType = chartData.datasets.length > 0 && chartData.datasets[0].type ? chartData.datasets[0].type : 'line';

        chartInstances[indicatorId] = new Chart(ctx, {
            type: chartType,
            data: {
                labels: chartData.labels,
                datasets: chartData.datasets.map(ds => ({
                    ...ds,
                    borderColor: ds.borderColor || '#007bff',
                    backgroundColor: ds.backgroundColor || 'rgba(0, 123, 255, 0.5)',
                    tension: 0.1,
                    pointRadius: 1, // 讓線條更平滑
                    borderWidth: 2
                }))
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        type: 'time',
                        time: {
                            unit: 'month',
                            tooltipFormat: 'yyyy-MM-dd',
                            displayFormats: {
                                month: 'yyyy-MM'
                            }
                        },
                        title: {
                            display: true,
                            text: '日期'
                        }
                    },
                    y: {
                        beginAtZero: false,
                        title: {
                            display: true,
                            text: '數值'
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: chartData.datasets.length > 1, // 只有多個數據集時才顯示圖例
                        position: 'top',
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                    }
                },
                interaction: {
                    mode: 'index',
                    intersect: false,
                }
            }
        });
    }

    /**
     * 顯示錯誤或提示訊息在圖表容器中。
     * @param {string} indicatorId - 指標 ID。
     * @param {string} message - 要顯示的訊息。
     */
    function showChartMessage(indicatorId, message) {
        const container = document.querySelector(`.panel[data-indicator-id="${indicatorId}"] .chart-container`);
        if (container) {
            container.innerHTML = `<p class="placeholder">${message}</p>`;
        }
    }

    /**
     * 為單一指標異步獲取數據並觸發渲染。
     * @param {HTMLElement} panel - 圖表的容器 panel 元素。
     * @param {string} startDate - 開始日期 (YYYY-MM-DD)。
     * @param {string} endDate - 結束日期 (YYYY-MM-DD)。
     */
    async function loadAndRenderChart(panel, startDate, endDate) {
        const indicatorId = panel.dataset.indicatorId;
        const canvasId = `chart-canvas-${indicatorId}`;

        // 重置容器，放入 canvas
        const container = panel.querySelector('.chart-container');
        container.innerHTML = `<canvas id="${canvasId}"></canvas>`;

        showChartMessage(indicatorId, '圖表載入中...');

        try {
            const response = await fetch(`/api/chart_data/${indicatorId}?start_date=${startDate}&end_date=${endDate}`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || `HTTP 錯誤: ${response.status}`);
            }
            const data = await response.json();

            if (data.datasets.every(ds => ds.data.every(val => val === null))) {
                 showChartMessage(indicatorId, '此日期範圍內無可用數據。');
                 return;
            }

            renderChart(indicatorId, data);
        } catch (error) {
            console.error(`載入指標 '${indicatorId}' 失敗:`, error);
            showChartMessage(indicatorId, `圖表載入失敗: ${error.message}`);
        }
    }

    /**
     * 載入所有圖表。
     */
    function loadAllCharts() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;

        if (!startDate || !endDate) {
            alert("請確保已選擇開始和結束日期。");
            return;
        }

        if (new Date(startDate) >= new Date(endDate)) {
            alert("開始日期必須早於結束日期。");
            return;
        }

        console.log(`開始載入所有圖表，日期範圍: ${startDate} 至 ${endDate}`);

        chartPanels.forEach(panel => {
            loadAndRenderChart(panel, startDate, endDate);
        });
    }

    /**
     * 設定預設日期範圍。
     */
    function setDefaultDates() {
        const today = new Date();
        const endDate = today.toISOString().split('T')[0];

        // 預設開始日期為 2018-01-01
        const startDate = "2018-01-01";

        startDateInput.value = startDate;
        endDateInput.value = endDate;
        console.log(`已設定預設日期範圍: ${startDate} 至 ${endDate}`);
    }

    // --- 初始化與事件綁定 ---

    if (updateBtn) {
        updateBtn.addEventListener('click', loadAllCharts);
    } else {
        console.error("找不到更新按鈕元素。");
    }

    setDefaultDates();
    loadAllCharts();
});