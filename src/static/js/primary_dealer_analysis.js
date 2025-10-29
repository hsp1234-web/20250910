// src/static/js/primary_dealer_analysis.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("儀表板動態載入腳本 V7.0 已啟動 (整合指數退避重試機制)。");

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
    let fullData = {};

    const titleMapping = {
        "sofr": "SOFR (擔保隔夜融資利率)", "stress_index": "綜合壓力指數", "vix": "VIX (恐慌指數)",
        "us_bond_2y_10y_spread": "美債2年與10年利差", "us_high_yield_spread": "高收益債利差",
        "stress_index_macd": "壓力指數 MACD", "dealer_net_positions": "一級交易商淨部位",
        "dealer_long_term_positions": "一級交易商長天期部位", "dealer_short_term_positions": "一級交易商短天期部位",
        "dealer_net_position_ranking": "各類部位最新淨值排名", "dealer_position_change_ranking": "各類部位最新變動排名",
        "ofr_fci": "OFR 金融壓力指數"
    };
    const indicators = Array.from(document.querySelectorAll('.panel[data-indicator-id]')).map(panel => panel.dataset.indicatorId);

    // --- 核心流程重構 ---

    function setPlaceholderMessage(message, color = '#888') {
        indicators.forEach(id => {
            const container = document.getElementById(`chart-container-${id}`);
            if (container) {
                container.innerHTML = `<div class="placeholder" style="color: ${color};">${message}</div>`;
            }
        });
    }

    // 新增：帶有指數退避的健康檢查函式
    async function waitForServiceReady() {
        const maxRetries = 8;
        let delay = 2000; // 初始延遲 2 秒

        for (let i = 0; i < maxRetries; i++) {
            try {
                const response = await fetch('/api/bond_service/health');
                if (response.ok) {
                    console.log("✅ 後端分析服務已就緒。");
                    return true;
                }
            } catch (error) {
                // 忽略網路錯誤，繼續重試
                console.warn(`健康檢查失敗 (第 ${i + 1} 次)，服務可能尚未啟動。`);
            }

            if (i < maxRetries - 1) {
                setPlaceholderMessage(`正在等待後端分析服務啟動... (第 ${i + 1}/${maxRetries} 次嘗試)`);
                await new Promise(resolve => setTimeout(resolve, delay));
                delay *= 2; // 指數增加延遲
            }
        }

        console.error("等待後端分析服務超时。");
        return false;
    }


    async function handleAnalysisClick() {
        const startDate = startDateInput.value;
        const endDate = endDateInput.value;
        if (!startDate || !endDate) {
            alert("請確保已選擇開始和結束日期。");
            return;
        }

        updateBtn.disabled = true;
        setPlaceholderMessage("正在初始化分析...");

        // 步骤 1: 等待服务就绪
        const isServiceReady = await waitForServiceReady();
        if (!isServiceReady) {
            setPlaceholderMessage("後端分析服務目前無法連線，請稍後再試。", "#d63031");
            updateBtn.disabled = false;
            return;
        }

        // 步骤 2: 探测数据状态或轮询
        await pollDataStatus(startDate, endDate);
    }

    async function pollDataStatus(startDate, endDate) {
        const probeIndicator = 'stress_index';
        const probeApiUrl = `/api/bond_service/data/${probeIndicator}?start_date=${startDate}&end_date=${endDate}`;

        try {
            const response = await fetch(probeApiUrl);

            if (response.status === 200) {
                console.log("資料已在快取中就緒，開始載入所有圖表。");
                setPlaceholderMessage("圖表載入中...");
                await fetchAllChartsData(startDate, endDate);
            } else if (response.status === 202) {
                console.log("後端正在準備數據，5 秒後將自動重試...");
                const data = await response.json();
                setPlaceholderMessage(data.message || "正在從外部來源獲取最新數據，請稍候...");
                setTimeout(() => pollDataStatus(startDate, endDate), 5000);
            } else {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `伺服器返回未預期的狀態: ${response.status}`);
            }
        } catch (error) {
            console.error("探測資料狀態時發生錯誤:", error);
            setPlaceholderMessage(`載入失敗：${error.message}`, "#d63031");
            updateBtn.disabled = false;
        }
    }

    async function fetchAllChartsData(startDate, endDate) {
        // ... (此函數內容未變)
        console.log(`啟動所有圖表的併發載入程序...`);
        fullData = {}; // 重設數據

        const chartLoadPromises = indicators.map(indicatorId => (async () => {
            const apiUrl = `/api/bond_service/data/${indicatorId}?start_date=${startDate}&end_date=${endDate}`;
            try {
                const response = await fetch(apiUrl);
                if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `請求失敗: ${response.statusText}`);
                const chartData = await response.json();
                if (!chartData || chartData.length === 0) {
                    console.warn(`指標 '${indicatorId}' 沒有返回數據。`);
                    const container = document.getElementById(`chart-container-${indicatorId}`);
                    if (container) container.innerHTML = `<div class="placeholder">無可用數據</div>`;
                    return;
                }
                fullData[indicatorId] = chartData;
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
        updateBtn.disabled = false;
    }

    // --- 以下為圖表繪製和頁面互動邏輯 (未變動) ---
    async function plotChartFromData(indicatorId, data) {
        const container = document.getElementById(`chart-container-${indicatorId}`);
        try {
            const plotFunction = getPlotFunction(indicatorId);
            await plotFunction(container, data, indicatorId, false);
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
            plotFunction(modalChartContainer, fullData[indicatorId], indicatorId, true)
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
    }

    // --- 初始化與事件綁定 ---
    if (updateBtn) {
        updateBtn.addEventListener('click', handleAnalysisClick);
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
