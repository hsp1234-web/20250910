// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("Bond Analysis Page script loaded.");

    const API_BASE_URL = "http://127.0.0.1:36109"; // Port from orchestrator logs, for dev
    const chartInstances = {}; // To hold our chart objects

    const indicators = [
        { id: 'gdp', chartId: 'gdp-chart', label: '美國實質GDP (十億美元)' },
        { id: 'cpi', chartId: 'cpi-chart', label: '美國CPI' },
        { id: 'fedfunds', chartId: 'fedfunds-chart', label: '聯準會基準利率 (%)' }
    ];

    // Function to render a chart
    function renderChart(chartId, label, labels, data) {
        const ctx = document.getElementById(chartId);
        if (!ctx) {
            console.error(`Canvas with id ${chartId} not found.`);
            return;
        }

        // Destroy previous chart instance if it exists
        if (chartInstances[chartId]) {
            chartInstances[chartId].destroy();
        }

        chartInstances[chartId] = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: label,
                    data: data,
                    borderColor: 'rgba(0, 123, 255, 1)',
                    backgroundColor: 'rgba(0, 123, 255, 0.1)',
                    fill: true,
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: false
                    }
                }
            }
        });
    }

    // Function to fetch data and render a chart
    async function fetchAndRenderChart(indicator) {
        const { id, chartId, label } = indicator;
        const statusEl = document.getElementById(`${id}-last-updated`);
        try {
            statusEl.textContent = '載入中...';
            const response = await fetch(`${API_BASE_URL}/data/${id}`);
            if (!response.ok) {
                throw new Error(`Network response was not ok: ${response.statusText}`);
            }
            const rawData = await response.json();

            if (rawData.length === 0) {
                statusEl.textContent = '尚無資料';
                return;
            }

            const labels = rawData.map(d => d.date);
            const data = rawData.map(d => d.value);

            renderChart(chartId, label, labels, data);

            // Update last updated time
            const lastDate = labels[labels.length - 1];
            statusEl.textContent = lastDate ? new Date(lastDate).toLocaleDateString('zh-TW') : 'N/A';

        } catch (error) {
            console.error(`Failed to fetch or render ${id}:`, error);
            statusEl.textContent = '讀取失敗';
        }
    }

    // Initial load of all charts
    function loadAllCharts() {
        console.log("Loading all charts...");
        indicators.forEach(fetchAndRenderChart);
    }

    // --- Manual Update Logic ---
    async function handleFetchClick(indicator) {
        const { id } = indicator;
        const button = document.getElementById(`btn-fetch-${id}`);
        const statusDiv = document.getElementById('update-status');

        if (!button) return;

        button.disabled = true;
        button.textContent = '更新中...';
        statusDiv.textContent = `正在為 ${id.toUpperCase()} 觸發伺服器端資料更新...`;

        try {
            const response = await fetch(`${API_BASE_URL}/fetch/${id}`, { method: 'POST' });
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || '伺服器返回錯誤');
            }

            statusDiv.textContent = `✅ ${result.message} 現在將刷新圖表。`;

            // Fetch and re-render the chart with new data
            await fetchAndRenderChart(indicator);

        } catch (error) {
            console.error(`Failed to trigger fetch for ${id}:`, error);
            statusDiv.textContent = `❌ 更新 ${id.toUpperCase()} 失敗: ${error.message}`;
        } finally {
            button.disabled = false;
            button.textContent = `更新${id.toUpperCase()}數據`;
        }
    }

    // Add event listeners to buttons
    indicators.forEach(indicator => {
        const button = document.getElementById(`btn-fetch-${indicator.id}`);
        if (button) {
            button.addEventListener('click', () => handleFetchClick(indicator));
        }
    });

    loadAllCharts();
});
