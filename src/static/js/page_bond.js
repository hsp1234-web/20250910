// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("Bond Analysis Page script loaded.");

    let apiBaseUrl = null; // 將動態設定
    const chartInstances = {}; // 用來存放我們的圖表物件

    // --- 服務發現 ---
    async function getApiBaseUrl() {
        if (apiBaseUrl) {
            return apiBaseUrl;
        }
        try {
            console.log("正在從主應用程式獲取服務註冊資訊...");
            const response = await fetch('/api/service_registry');
            if (!response.ok) {
                throw new Error('無法獲取服務註冊資訊。');
            }
            const registry = await response.json();
            const bondServiceInfo = registry['bond_data_service'];
            if (!bondServiceInfo || !bondServiceInfo.port) {
                throw new Error('在註冊資訊中找不到 bond_data_service 的埠號。');
            }
            apiBaseUrl = `http://127.0.0.1:${bondServiceInfo.port}`;
            console.log(`服務發現成功！ Bond Data Service 位址: ${apiBaseUrl}`);
            return apiBaseUrl;
        } catch (error) {
            console.error("服務發現失敗:", error);
            const statusDiv = document.getElementById('update-status');
            if(statusDiv) statusDiv.textContent = `❌ 錯誤：無法連接到後端微服務。請確認主服務和子服務都已啟動。 ${error.message}`;
            throw error; // 重新拋出錯誤以停止後續執行
        }
    }

    const indicators = [
        { id: 'gdp', chartId: 'gdp-chart', label: '美國實質GDP (十億美元)' },
        { id: 'cpi', chartId: 'cpi-chart', label: '美國CPI' },
        { id: 'fedfunds', chartId: 'fedfunds-chart', label: '聯準會基準利率 (%)' }
    ];

    // 渲染圖表的函式
    function renderChart(chartId, label, labels, data) {
        const ctx = document.getElementById(chartId);
        if (!ctx) {
            console.error(`找不到 ID 為 ${chartId} 的 canvas。`);
            return;
        }

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
                scales: { y: { beginAtZero: false } }
            }
        });
    }

    // 抓取數據並渲染圖表的函式
    async function fetchAndRenderChart(indicator) {
        const { id, chartId, label } = indicator;
        const statusEl = document.getElementById(`${id}-last-updated`);
        try {
            const baseUrl = await getApiBaseUrl();
            statusEl.textContent = '載入中...';
            const response = await fetch(`${baseUrl}/data/${id}`);
            if (!response.ok) {
                throw new Error(`網路回應不正常: ${response.statusText}`);
            }
            const rawData = await response.json();

            if (rawData.length === 0) {
                // 如果沒有資料，自動觸發一次抓取
                console.log(`指標 '${id}' 在資料庫中沒有資料，正在觸發自動抓取...`);
                statusEl.textContent = '首次載入，正在從遠端更新...';
                await handleFetchClick({ id, chartId, label }); // 自動觸發更新
                return; // handleFetchClick 會處理後續的渲染
            }

            const labels = rawData.map(d => d.date);
            const data = rawData.map(d => d.value);

            renderChart(chartId, label, labels, data);

            const lastDate = labels[labels.length - 1];
            statusEl.textContent = lastDate ? new Date(lastDate).toLocaleDateString('zh-TW') : 'N/A';

        } catch (error) {
            console.error(`抓取或渲染 ${id} 失敗:`, error);
            statusEl.textContent = '讀取失敗';
        }
    }

    // 初始載入所有圖表
    function loadAllCharts() {
        getApiBaseUrl().then(() => {
            console.log("正在載入所有圖表...");
            indicators.forEach(fetchAndRenderChart);
        }).catch(error => {
            console.error("因服務位址獲取失敗，無法載入圖表。");
        });
    }

    // --- 手動更新邏輯 ---
    async function handleFetchClick(indicator) {
        const { id } = indicator;
        const button = document.getElementById(`btn-fetch-${id}`);
        const statusDiv = document.getElementById('update-status');

        if (!button) return;

        button.disabled = true;
        button.textContent = '更新中...';
        statusDiv.textContent = `正在為 ${id.toUpperCase()} 觸發伺服器端資料更新...`;

        try {
            const baseUrl = await getApiBaseUrl();
            const response = await fetch(`${baseUrl}/fetch/${id}`, { method: 'POST' });
            const result = await response.json();

            if (!response.ok) {
                throw new Error(result.detail || '伺服器返回錯誤');
            }

            statusDiv.textContent = `✅ ${result.message} 現在將刷新圖表。`;

            await fetchAndRenderChart(indicator);

        } catch (error) {
            console.error(`觸發 ${id} 的抓取失敗:`, error);
            statusDiv.textContent = `❌ 更新 ${id.toUpperCase()} 失敗: ${error.message}`;
        } finally {
            button.disabled = false;
            button.textContent = `更新${id.toUpperCase()}數據`;
        }
    }

    // 為按鈕加上事件監聽器
    indicators.forEach(indicator => {
        const button = document.getElementById(`btn-fetch-${indicator.id}`);
        if (button) {
            button.addEventListener('click', () => handleFetchClick(indicator));
        }
    });

    loadAllCharts();
});
