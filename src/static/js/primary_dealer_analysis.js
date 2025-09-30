// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("儀表板動態載入腳本 V5.0 已啟動 (整合互動圖表)。");

    // --- 元素選擇器 ---
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const updateBtn = document.getElementById('update-charts-btn');
    const grid = document.querySelector('.dashboard-grid');
    const modal = document.getElementById('interactive-chart-modal');
    const modalTitle = document.getElementById('modal-chart-title');
    const modalChartContainer = document.getElementById('modal-chart-container');
    const modalCloseBtn = document.getElementById('modal-close-btn');

    // --- 全域變數 ---
    let fullData = {}; // 用於儲存從後端獲取的完整數據，供互動圖表使用

    // 中文標題的對應表
    const titleMapping = {
        "sofr": "SOFR (擔保隔夜融資利率)", "stress_index": "綜合壓力指數", "vix": "VIX (恐慌指數)",
        "us_bond_2y_10y_spread": "美債2年與10年利差", "us_high_yield_spread": "高收益債利差",
        "stress_index_macd": "壓力指數 MACD", "dealer_net_positions": "一級交易商淨部位",
        "dealer_long_term_positions": "一級交易商長天期部位", "dealer_short_term_positions": "一級交易商短天期部位",
        "dealer_net_position_ranking": "各類部位最新淨值排名", "dealer_position_change_ranking": "各類部位最新變動排名",
        "ofr_fci": "OFR 金融壓力指數"
    };

    const indicators = Array.from(document.querySelectorAll('.panel[data-indicator-id]')).map(panel => panel.dataset.indicatorId);

    async function checkServiceHealth() {
        try {
            const response = await fetch('/api/bond_service/health');
            return response.ok;
        } catch (error) {
            console.warn("健康檢查請求失敗，服務可能尚未就緒。");
            return false;
        }
    }

    async function checkKeyAndLoadCharts() {
        console.log("✅ 後端服務已就緒！正在檢查 FRED API 金鑰...");

        // 檢查 FRED API 金鑰狀態
        try {
            const keyResponse = await fetch('/api/key_status/fred');
            if (!keyResponse.ok) {
                throw new Error(`伺服器錯誤: ${keyResponse.status}`);
            }

            const keyStatus = await keyResponse.json();

            if (keyStatus.available) {
                console.log("✅ FRED API 金鑰已就緒，開始載入圖表。");
                loadAllCharts();
            } else {
                const message = "後端尚未設定 FRED API 金鑰，圖表功能無法使用。";
                console.warn(message);
                indicators.forEach(id => {
                    document.getElementById(`chart-container-${id}`).innerHTML = `<div class="placeholder" style="color: #d63031;">${message}</div>`;
                });
            }
        } catch (error) {
            console.error("檢查 FRED API 金鑰狀態時發生網路錯誤:", error);
            const message = "網路錯誤，無法檢查 FRED 金鑰狀態。";
            indicators.forEach(id => {
                document.getElementById(`chart-container-${id}`).innerHTML = `<div class="placeholder" style="color: #d63031;">${message}</div>`;
            });
        }
    }

    function waitForServiceReady() {
        // 顯示載入提示
        indicators.forEach(id => {
            const container = document.getElementById(`chart-container-${id}`);
            if (container) container.innerHTML = '<div class="placeholder">正在等待後端服務啟動...</div>';
        });

        // 使用輪詢來探測後端服務
        const intervalId = setInterval(async () => {
            console.log("正在探測後端服務狀態...");
            if (await checkServiceHealth()) {
                clearInterval(intervalId);
                checkKeyAndLoadCharts(); // 服務就緒後，交由下一步處理
            } else {
                console.log("...後端服務尚未就緒，將在 2 秒後重試。");
            }
        }, 2000);
    }

    async function loadAllCharts() {
        const startDate = startDateInput.value, endDate = endDateInput.value;
        if (!startDate || !endDate) { alert("請確保已選擇開始和結束日期。"); return; }
        console.log(`啟動獨立圖表載入程序...`);
        fullData = {}; // 重設數據

        const allPanels = Array.from(document.querySelectorAll('.panel[data-indicator-id]'));
        allPanels.forEach(panel => {
            panel.style.height = 'auto';
            const container = panel.querySelector('.chart-container');
            if (container) container.innerHTML = '<div class="placeholder">圖表載入中...</div>';
        });

        const chartLoadPromises = indicators.map(indicatorId => (async () => {
            const apiUrl = `/api/bond_service/data/${indicatorId}?start_date=${startDate}&end_date=${endDate}`;
            try {
                const response = await fetch(apiUrl);
                if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `請求失敗: ${response.statusText}`);
                const chartData = await response.json();
                if (!chartData || chartData.length === 0) throw new Error('後端未返回任何數據');

                fullData[indicatorId] = chartData; // 儲存數據
                await plotChartFromData(indicatorId, chartData);
            } catch (error) {
                console.error(`載入圖表 ${indicatorId} 發生錯誤:`, error);
                const container = document.getElementById(`chart-container-${indicatorId}`);
                if (container) container.innerHTML = `<div class="placeholder" style="color: #d63031;">載入失敗<br><small>${error.message}</small></div>`;
                return Promise.reject(error);
            }
        })());

        await Promise.allSettled(chartLoadPromises);
        console.log("所有圖表載入流程已完成。");
        alignAllCharts();
    }

    async function plotChartFromData(indicatorId, data) {
        const container = document.getElementById(`chart-container-${indicatorId}`);
        try {
            const plotFunction = getPlotFunction(indicatorId);
            await plotFunction(container, data, indicatorId, false); // false for isInteractive
            const dataUrl = await Plotly.toImage(container, { format: 'png', width: container.offsetWidth, height: container.offsetHeight, scale: 2 });
            const img = document.createElement('img');
            img.src = dataUrl;
            img.style.cursor = 'pointer';
            img.addEventListener('click', () => openInteractiveChart(indicatorId));
            container.innerHTML = '';
            container.appendChild(img);
        } catch (error) {
            console.error(`繪製圖表 ${indicatorId} 發生錯誤:`, error);
            container.innerHTML = `<div class="placeholder" style="color: #d63031;">繪製失敗<br><small>${error.message}</small></div>`;
        }
    }

    function openInteractiveChart(indicatorId) {
        if (!fullData[indicatorId]) { console.error(`找不到指標 ${indicatorId} 的互動數據。`); return; }
        modalTitle.textContent = titleMapping[indicatorId] || "互動圖表";
        modalChartContainer.innerHTML = '<div class="placeholder">正在載入互動圖表...</div>';
        modal.style.display = 'flex';
        setTimeout(() => {
            const plotFunction = getPlotFunction(indicatorId);
            plotFunction(modalChartContainer, fullData[indicatorId], indicatorId, true) // true for isInteractive
                .catch(err => {
                    console.error("繪製互動圖表時出錯:", err);
                    modalChartContainer.innerHTML = `<div class="placeholder" style="color:red;">互動圖表繪製失敗</div>`;
                });
        }, 50);
    }

    function closeInteractiveChart() {
        modal.style.display = 'none';
        Plotly.purge(modalChartContainer);
        modalChartContainer.innerHTML = '';
    }

    function getPlotFunction(indicatorId) {
        const plotMapping = {
            "sofr": plotSimpleLineChart, "ofr_fci": plotSimpleLineChart, "vix": plotSimpleLineChart,
            "us_bond_2y_10y_spread": plotSpreadChart, "us_high_yield_spread": plotSimpleLineChart,
            "stress_index": plotStressIndexChart, "dealer_net_positions": plotSimpleLineChart,
            "dealer_long_term_positions": plotSimpleLineChart, "dealer_short_term_positions": plotSimpleLineChart,
            "dealer_net_position_ranking": plotRankingBarChart, "dealer_position_change_ranking": plotChangeRankingBarChart,
            "stress_index_macd": plotMacdChart,
        };
        return plotMapping[indicatorId] || plotSimpleLineChart;
    }

    // --- 通用繪圖函式 (全中文化) ---
    // 主要修改：增加 isInteractive 參數以控制 staticPlot
    function plotSimpleLineChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId] || "圖表";
        const yAxisTitleMapping = {
            'sofr': '利率 (%)', 'us_high_yield_spread': '利差 (%)', 'vix': '指數值', 'ofr_fci': '指數值',
            'dealer_net_positions': '金額 (十億美元)', 'dealer_long_term_positions': '金額 (十億美元)', 'dealer_short_term_positions': '金額 (十億美元)',
        };
        const dataKey = Object.keys(data[0]).find(k => k !== 'date');
        let yValues = data.map(d => d[dataKey]);
        if (indicatorId.includes('positions')) yValues = yValues.map(v => v ? v / 1000 : null);
        const traces = [{ x: data.map(d => d.date), y: yValues, type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = { title: isInteractive ? chartTitle : '', xaxis: { title: '日期' }, yaxis: { title: yAxisTitleMapping[indicatorId] || '數值' }, margin: { l: 60, r: 40, t: isInteractive ? 60 : 40, b: 60 }, template: 'plotly_white', showlegend: false };
        return Plotly.newPlot(container, traces, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function plotStressIndexChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId];
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = {
            title: isInteractive ? chartTitle : '', xaxis: { title: '日期' }, yaxis: { title: '指數 (0-100)', range: [0, 100] },
            shapes: [ { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 60, x1: 1, y1: 80, fillcolor: 'rgba(255, 255, 0, 0.2)', layer: 'below', line: {width: 0}}, { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 80, x1: 1, y1: 100, fillcolor: 'rgba(255, 0, 0, 0.2)', layer: 'below', line: {width: 0}} ],
            annotations: [ { xref: 'paper', yref: 'y', x: 0.98, y: 70, text: '高壓力區', showarrow: false, font: { color: 'orange' } }, { xref: 'paper', yref: 'y', x: 0.98, y: 90, text: '極端壓力區', showarrow: false, font: { color: 'red' } } ],
            margin: { l: 60, r: 40, t: isInteractive ? 60 : 40, b: 60 }, template: 'plotly_white', showlegend: false
        };
        return Plotly.newPlot(container, traces, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function plotSpreadChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId];
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.spread_10y2y * 100), type: 'scatter', mode: 'lines', name: '利差' }];
        const layout = { title: isInteractive ? chartTitle : '', xaxis: { title: '日期' }, yaxis: { title: '基點 (BPS)' }, shapes: [{ type: 'line', xref: 'paper', yref: 'y', x0: 0, y0: 0, x1: 1, y1: 0, line: { color: 'grey', dash: 'dash' }}], margin: { l: 60, r: 40, t: isInteractive ? 60 : 40, b: 60 }, template: 'plotly_white', showlegend: false };
        return Plotly.newPlot(container, traces, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function plotMacdChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId];
        const dates = data.map(d => d.date);
        const macdHist = data.map(d => d.macd_hist);
        const plotData = [
            { x: dates, y: data.map(d => d.macd_line), type: 'scatter', mode: 'lines', name: 'MACD 線', yaxis: 'y2' },
            { x: dates, y: data.map(d => d.macd_signal_line), type: 'scatter', mode: 'lines', name: '訊號線', yaxis: 'y2' },
            { x: dates, y: macdHist, type: 'bar', name: 'MACD 柱', yaxis: 'y2', marker: { color: macdHist.map(v => v >= 0 ? 'rgba(214, 48, 49, 0.7)' : 'rgba(0, 184, 148, 0.7)') } },
            { x: dates, y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: '壓力指數', yaxis: 'y1' }
        ];
        const layout = { title: isInteractive ? chartTitle : '', xaxis: { title: '日期' }, yaxis: { title: '壓力指數', side: 'left' }, yaxis2: { title: 'MACD', overlaying: 'y', side: 'right', showgrid: false }, legend: { x: 0, y: 1.15, orientation: 'h' }, margin: { l: 50, r: 50, t: 80, b: 50 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function plotRankingBarChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId];
        const latestData = data[data.length - 1];
        const positions = { "淨部位": latestData.dealer_net_positions, "長天期": latestData.dealer_long_term_positions, "短天期": latestData.dealer_short_term_positions };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const plotData = [{ x: sortedPositions.map(([,v]) => v ? v / 1000 : 0), y: sortedPositions.map(([k,]) => k), type: 'bar', orientation: 'h', text: sortedPositions.map(([,v]) => v ? (v/1000).toFixed(2) : "N/A"), textposition: 'inside' }];
        const layout = { title: isInteractive ? chartTitle : '', xaxis: { title: '金額 (十億美元)' }, yaxis: { title: '部位類型' }, margin: { l: 80, r: 40, t: isInteractive ? 60 : 40, b: 60 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function plotChangeRankingBarChart(container, data, indicatorId, isInteractive) {
        const chartTitle = titleMapping[indicatorId];
        if (data.length < 2) { container.innerHTML = '<div class="placeholder">數據不足</div>'; return; }
        const latest = data[data.length - 1], previous = data[data.length - 2];
        const positions = { "淨部位": (latest.dealer_net_positions - previous.dealer_net_positions), "長天期": (latest.dealer_long_term_positions - previous.dealer_long_term_positions), "短天期": (latest.dealer_short_term_positions - previous.dealer_short_term_positions) };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const values = sortedPositions.map(([,v]) => v ? v / 1000 : 0);
        const plotData = [{ x: values, y: sortedPositions.map(([k,]) => k), type: 'bar', orientation: 'h', text: values.map(v => v.toFixed(2)), textposition: 'inside', marker: { color: values.map(v => v >= 0 ? '#2ca02c' : '#d62728') } }];
        const layout = { title: isInteractive ? chartTitle : '', xaxis: { title: '變動金額 (十億美元)' }, yaxis: { title: '部位類型' }, margin: { l: 80, r: 40, t: isInteractive ? 60 : 40, b: 60 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true, staticPlot: !isInteractive });
    }

    function alignChartPanels(panels) {
        if (!panels || panels.length === 0) return;
        const maxHeight = Math.max(...panels.map(p => p.offsetHeight));
        if (maxHeight > 0) panels.forEach(p => { p.style.height = `${maxHeight}px`; });
    }

    function alignAllCharts() {
        const allPanels = Array.from(document.querySelectorAll('.panel[data-indicator-id]'));
        if (allPanels.length === 0) return;
        allPanels.forEach(panel => { panel.style.height = 'auto'; });
        const columns = Math.max(1, Math.floor(grid.offsetWidth / 500));
        for (let i = 0; i < allPanels.length; i += columns) {
            alignChartPanels(allPanels.slice(i, i + columns));
        }
        console.log("所有圖表已重新對齊。");
    }

    function setDefaultDates() {
        endDateInput.value = new Date().toISOString().split('T')[0];
        startDateInput.value = "2020-01-01";
        console.log(`已設定預設日期範圍: ${startDateInput.value} 至 ${endDateInput.value}`);
    }

    // --- 初始化與事件綁定 ---
    if (updateBtn) {
        updateBtn.addEventListener('click', waitForServiceReady);
    } else {
        console.error("找不到分析按鈕元素。");
    }

    modalCloseBtn.addEventListener('click', closeInteractiveChart);
    modal.addEventListener('click', (e) => { if (e.target === modal) closeInteractiveChart(); });

    let resizeTimer;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(alignAllCharts, 200);
    });

    setDefaultDates();
    console.log("儀表板已就緒，請點擊「開始分析」按鈕以載入圖表。");
});