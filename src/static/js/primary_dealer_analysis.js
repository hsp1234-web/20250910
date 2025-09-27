// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("儀表板動態載入腳本 V3.0 已啟動 (新增健康檢查)。");

    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');
    const grid = document.querySelector('.dashboard-grid');

    // 從 HTML 中自動獲取所有指標 ID
    const chartPanels = document.querySelectorAll('.panel[data-indicator-id]');
    const indicators = Array.from(chartPanels).map(panel => panel.dataset.indicatorId);

    /**
     * 檢查後端服務是否就緒
     * @returns {Promise<boolean>}
     */
    async function checkServiceHealth() {
        try {
            const response = await fetch('/api/bond_service/health');
            return response.ok;
        } catch (error) {
            console.warn("健康檢查請求失敗，服務可能尚未就緒。");
            return false;
        }
    }

    /**
     * 輪詢健康檢查端點，直到服務就緒為止
     */
    function waitForServiceReady() {
        // 先將所有圖表容器設置為「等待服務」狀態
        indicators.forEach(id => {
            const container = document.getElementById(`chart-container-${id}`);
            if (container) {
                container.innerHTML = '<div class="placeholder">正在等待後端服務啟動...</div>';
            }
        });

        const intervalId = setInterval(async () => {
            console.log("正在探測後端服務狀態...");
            const isReady = await checkServiceHealth();
            if (isReady) {
                console.log("✅ 後端服務已就緒！");
                clearInterval(intervalId); // 停止輪詢
                loadAllCharts(); // 開始載入所有圖表
            } else {
                console.log("...後端服務尚未就緒，將在 2 秒後重試。");
            }
        }, 2000); // 每 2 秒檢查一次
    }


    /**
     * 載入所有圖表的核心函式，採用分批循序載入策略。
     */
    async function loadAllCharts() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;

        if (!startDate || !endDate) {
            alert("請確保已選擇開始和結束日期。");
            return;
        }
        console.log(`啟動分批循序載入程序...`);

        // 在開始前重設所有面板的高度
        const allPanels = Array.from(document.querySelectorAll('.panel[data-indicator-id]'));
        allPanels.forEach(p => p.style.height = 'auto');

        // 步驟 1: 動態計算每列的圖表數量
        const grid = document.querySelector('.dashboard-grid');
        // 使用 CSS 中設定的最小寬度 500px 作為計算基準
        const panelMinWidth = 500;
        const columns = Math.max(1, Math.floor(grid.offsetWidth / panelMinWidth));
        console.log(`偵測到每列可容納 ${columns} 個圖表。`);

        // 步驟 2: 將指標陣列分批
        const chunks = [];
        for (let i = 0; i < indicators.length; i += columns) {
            chunks.push(indicators.slice(i, i + columns));
        }
        console.log(`已將圖表分為 ${chunks.length} 批進行載入。`);

        // 步驟 3: 循序處理每一批
        for (const chunk of chunks) {
            console.log(`正在載入批次: ${chunk.join(', ')}`);

            const currentBatchPanels = chunk.map(id => document.querySelector(`.panel[data-indicator-id="${id}"]`));

            const promises = chunk.map(indicatorId => {
                const container = document.getElementById(`chart-container-${indicatorId}`);
                if (container) {
                    container.innerHTML = '<div class="placeholder">圖表載入中...</div>';
                    return fetchAndPlotChart(indicatorId, startDate, endDate);
                }
                return Promise.resolve();
            });

            // 等待當前批次的圖表全部載入
            await Promise.all(promises);
            console.log(`批次 ${chunk.join(', ')} 載入完成。`);

            // 步驟 4: 對剛剛載入完成的這一列進行對齊
            alignChartPanels(currentBatchPanels);
        }

        console.log("所有圖表批次均已載入並對齊。");
    }

    /**
     * 根據指標 ID 獲取數據並繪製圖表
     * @param {string} indicatorId - 指標的唯一 ID
     * @param {string} startDate - 開始日期
     * @param {string} endDate - 結束日期
     */
    async function fetchAndPlotChart(indicatorId, startDate, endDate) {
        const container = document.getElementById(`chart-container-${indicatorId}`);
        const apiUrl = `/api/bond_service/data/${indicatorId}?start_date=${startDate}&end_date=${endDate}`;

        try {
            const response = await fetch(apiUrl);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({'error': `數據請求失敗: ${response.statusText}`}));
                throw new Error(errorData.error || `數據請求失敗: ${response.statusText}`);
            }
            const data = await response.json();

            if (!data || data.length === 0 || data.error) {
                throw new Error(data.error || '無可用數據');
            }

            const plotFunction = getPlotFunction(indicatorId);
            await plotFunction(container, data, indicatorId);

        } catch (error) {
            console.error(`載入圖表 ${indicatorId} 時發生錯誤:`, error);
            container.innerHTML = `<div class="placeholder" style="text-align: center; color: #d63031;">圖表載入失敗<br><small>${error.message}</small></div>`;
        }
    }

    /**
     * 根據指標 ID 返回對應的繪圖函式
     */
    function getPlotFunction(indicatorId) {
        const plotMapping = {
            "sofr": plotSimpleLineChart,
            "ofr_fci": plotSimpleLineChart,
            "vix": plotSimpleLineChart,
            "us_bond_2y_10y_spread": plotSpreadChart,
            "us_high_yield_spread": plotSimpleLineChart,
            "stress_index": plotStressIndexChart,
            "dealer_net_positions": plotSimpleLineChart,
            "dealer_long_term_positions": plotSimpleLineChart,
            "dealer_short_term_positions": plotSimpleLineChart,
            "dealer_net_position_ranking": plotRankingBarChart,
            "dealer_position_change_ranking": plotChangeRankingBarChart,
            "stress_index_macd": plotMacdChart,
        };
        return plotMapping[indicatorId] || plotSimpleLineChart;
    }

    // --- 通用繪圖函式 (全中文化) ---

    function plotSimpleLineChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        const yAxisTitleMapping = {
            'sofr': '利率 (%)',
            'us_high_yield_spread': '利差 (%)',
            'vix': '指數值',
            'ofr_fci': '指數值',
            'dealer_net_positions': '金額 (十億美元)',
            'dealer_long_term_positions': '金額 (十億美元)',
            'dealer_short_term_positions': '金額 (十億美元)',
        };
        const dataKey = Object.keys(data[0]).find(k => k !== 'date');
        let yValues = data.map(d => d[dataKey]);

        if (indicatorId.includes('positions')) {
             yValues = yValues.map(v => v ? v / 1000 : null);
        }

        const traces = [{ x: data.map(d => d.date), y: yValues, type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = {
            title: chartTitle,
            xaxis: { title: '日期' },
            yaxis: { title: yAxisTitleMapping[indicatorId] || '數值' },
            margin: { l: 60, r: 20, t: 40, b: 40 }, template: 'plotly_white', showlegend: false
        };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotStressIndexChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = {
            title: chartTitle,
            xaxis: { title: '日期' },
            yaxis: { title: '指數 (0-100)', range: [0, 100] },
            shapes: [
                { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 60, x1: 1, y1: 80, fillcolor: 'rgba(255, 255, 0, 0.2)', layer: 'below', line: {width: 0}},
                { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 80, x1: 1, y1: 100, fillcolor: 'rgba(255, 0, 0, 0.2)', layer: 'below', line: {width: 0}}
            ],
            annotations: [
                { xref: 'paper', yref: 'y', x: 0.98, y: 70, text: '高壓力區', showarrow: false, font: { color: 'orange' } },
                { xref: 'paper', yref: 'y', x: 0.98, y: 90, text: '極端壓力區', showarrow: false, font: { color: 'red' } }
            ],
            margin: { l: 60, r: 20, t: 40, b: 40 }, template: 'plotly_white', showlegend: false
        };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotSpreadChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.spread_10y2y * 100), type: 'scatter', mode: 'lines', name: '利差' }];
        const layout = {
            title: chartTitle,
            xaxis: { title: '日期' },
            yaxis: { title: '基點 (BPS)' },
            shapes: [{ type: 'line', xref: 'paper', yref: 'y', x0: 0, y0: 0, x1: 1, y1: 0, line: { color: 'grey', dash: 'dash' }}],
            margin: { l: 60, r: 20, t: 40, b: 40 }, template: 'plotly_white', showlegend: false
        };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotMacdChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        const dates = data.map(d => d.date);
        const macdHist = data.map(d => d.macd_hist);
        const plotData = [
            { x: dates, y: data.map(d => d.macd_line), type: 'scatter', mode: 'lines', name: 'MACD 線', yaxis: 'y2' },
            { x: dates, y: data.map(d => d.macd_signal_line), type: 'scatter', mode: 'lines', name: '訊號線', yaxis: 'y2' },
            { x: dates, y: macdHist, type: 'bar', name: 'MACD 柱', yaxis: 'y2', marker: { color: macdHist.map(v => v >= 0 ? 'rgba(214, 48, 49, 0.7)' : 'rgba(0, 184, 148, 0.7)') } },
            { x: dates, y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: '壓力指數', yaxis: 'y1' }
        ];
        const layout = {
            title: chartTitle,
            xaxis: { title: '日期' },
            yaxis: { title: '壓力指數', side: 'left' },
            yaxis2: { title: 'MACD', overlaying: 'y', side: 'right', showgrid: false },
            legend: { x: 0, y: 1.15, orientation: 'h' }, margin: { l: 50, r: 50, t: 40, b: 50 }, template: 'plotly_white'
        };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    function plotRankingBarChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        const latestData = data[data.length - 1];
        const positions = {
            "淨部位": latestData.dealer_net_positions,
            "長天期": latestData.dealer_long_term_positions,
            "短天期": latestData.dealer_short_term_positions
        };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const plotData = [{
            x: sortedPositions.map(([,v]) => v ? v / 1000 : 0),
            y: sortedPositions.map(([k,]) => k),
            type: 'bar', orientation: 'h', text: sortedPositions.map(([,v]) => v ? (v/1000).toFixed(2) : "N/A"), textposition: 'inside'
        }];
        const layout = {
            title: chartTitle,
            xaxis: { title: '金額 (十億美元)' },
            yaxis: { title: '部位類型' },
            margin: { l: 80, r: 20, t: 40, b: 40 }, template: 'plotly_white'
        };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    function plotChangeRankingBarChart(container, data, indicatorId) {
        const chartTitle = container.parentElement.querySelector('h2').textContent;
        if (data.length < 2) {
            container.innerHTML = '<div class="placeholder">數據不足，無法計算變動</div>';
            return;
        }
        const latest = data[data.length - 1];
        const previous = data[data.length - 2];
        const positions = {
            "淨部位": (latest.dealer_net_positions - previous.dealer_net_positions),
            "長天期": (latest.dealer_long_term_positions - previous.dealer_long_term_positions),
            "短天期": (latest.dealer_short_term_positions - previous.dealer_short_term_positions)
        };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const values = sortedPositions.map(([,v]) => v ? v / 1000 : 0);
        const plotData = [{
            x: values, y: sortedPositions.map(([k,]) => k),
            type: 'bar', orientation: 'h', text: values.map(v => v.toFixed(2)), textposition: 'inside',
            marker: { color: values.map(v => v >= 0 ? '#2ca02c' : '#d62728') }
        }];
        const layout = {
            title: chartTitle,
            xaxis: { title: '變動金額 (十億美元)' },
            yaxis: { title: '部位類型' },
            margin: { l: 80, r: 20, t: 40, b: 40 }, template: 'plotly_white'
        };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    /**
     * 對齊指定的一批圖表卡片，確保它們等高。
     * @param {HTMLElement[]} panels - 需要對齊的 DOM 元素陣列 (通常是一列的 panel)。
     */
    function alignChartPanels(panels) {
        if (!panels || panels.length === 0) return;

        console.log(`正在對齊 ${panels.length} 個面板...`);

        // 由於現在能確保圖表已渲染完畢，可以直接計算高度，無需延遲
        // 找出這批面板中的最大高度
        const maxHeight = Math.max(...panels.map(p => p.offsetHeight));

        // 將這批面板的高度全部設置為最大值
        if (maxHeight > 0) {
            panels.forEach(p => {
                p.style.height = `${maxHeight}px`;
            });
            console.log(`面板已對齊至高度: ${maxHeight}px`);
        }
    }

    function setDefaultDates() {
        const today = new Date();
        const endDate = today.toISOString().split('T')[0];
        const startDate = "2020-01-01";
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

    // 新增：處理視窗大小變更事件，以重新觸發整個載入和對齊流程
    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        // 當視窗大小改變時，重新執行整個載入流程，以重新計算欄數和批次
        resizeTimer = setTimeout(loadAllCharts, 200);
    });

    setDefaultDates();
    // 啟動應用程式的主流程：等待服務就緒，然後載入圖表
    waitForServiceReady();
});