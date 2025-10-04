// src/static/js/interactive_chart.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("互動圖表檢視器腳本已啟動。");

    const chartContainer = document.getElementById('chart-container');
    const chartTitleElement = document.getElementById('chart-title');

    // 中文標題的對應表
    const titleMapping = {
        "sofr": "SOFR (擔保隔夜融資利率)",
        "stress_index": "綜合壓力指數",
        "vix": "VIX (恐慌指數)",
        "us_bond_2y_10y_spread": "美債2年與10年利差",
        "us_high_yield_spread": "高收益債利差",
        "stress_index_macd": "壓力指數 MACD",
        "dealer_net_positions": "一級交易商淨部位",
        "dealer_long_term_positions": "一級交易商長天期部位",
        "dealer_short_term_positions": "一級交易商短天期部位",
        "dealer_net_position_ranking": "各類部位最新淨值排名",
        "dealer_position_change_ranking": "各類部位最新變動排名",
        "ofr_fci": "OFR 金融壓力指數"
    };

    /**
     * 從 URL 查詢參數中獲取繪圖所需的資訊
     * @returns {{indicator: string, startDate: string, endDate: string, title: string} | null}
     */
    function getChartParamsFromURL() {
        const params = new URLSearchParams(window.location.search);
        const indicator = params.get('indicator');
        const startDate = params.get('start');
        const endDate = params.get('end');

        if (!indicator || !startDate || !endDate) {
            console.error("URL 參數不完整 (需要 indicator, start, end)。");
            return null;
        }

        const title = titleMapping[indicator] || "互動圖表";
        return { indicator, startDate, endDate, title };
    }

    /**
     * 載入並繪製互動圖表
     */
    async function loadInteractiveChart() {
        const params = getChartParamsFromURL();
        if (!params) {
            chartContainer.innerHTML = '<div class="placeholder" style="color: #d63031;">錯誤：缺少必要的圖表參數。</div>';
            return;
        }

        const { indicator, startDate, endDate, title } = params;
        chartTitleElement.textContent = title; // 更新頁面標題

        const apiUrl = `/api/bond_service/data/${indicator}?start_date=${startDate}&end_date=${endDate}`;

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

            const plotFunction = getPlotFunction(indicator);

            // 關鍵：直接呼叫繪圖函式，但不轉換為圖片
            // 繪圖函式內部需要移除 staticPlot: true
            chartContainer.innerHTML = ''; // 清空 placeholder
            await plotFunction(chartContainer, data, indicator);

        } catch (error) {
            console.error(`載入互動圖表 ${indicator} 時發生錯誤:`, error);
            chartContainer.innerHTML = `<div class="placeholder" style="text-align: center; color: #d63031;">圖表載入失敗<br><small>${error.message}</small></div>`;
        }
    }

    /**
     * 根據指標 ID 返回對應的繪圖函式
     */
    function getPlotFunction(indicatorId) {
        // 這些繪圖函式是從主頁面 JS 複製而來，但移除了 staticPlot 選項
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

    // --- 可互動的繪圖函式 (複製並修改自 primary_dealer_analysis.js) ---
    // 主要修改：移除 { staticPlot: true }，確保 responsive 為 true

    function plotSimpleLineChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId] || "圖表";
        const yAxisTitleMapping = {
            'sofr': '利率 (%)', 'us_high_yield_spread': '利差 (%)', 'vix': '指數值', 'ofr_fci': '指數值',
            'dealer_net_positions': '金額 (十億美元)', 'dealer_long_term_positions': '金額 (十億美元)', 'dealer_short_term_positions': '金額 (十億美元)',
        };
        const dataKey = Object.keys(data[0]).find(k => k !== 'date');
        let yValues = data.map(d => d[dataKey]);
        if (indicatorId.includes('positions')) yValues = yValues.map(v => v ? v / 1000 : null);
        const traces = [{ x: data.map(d => d.date), y: yValues, type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = { title: chartTitle, xaxis: { title: '日期' }, yaxis: { title: yAxisTitleMapping[indicatorId] || '數值' }, margin: { l: 60, r: 40, t: 60, b: 60 }, template: 'plotly_white', showlegend: false };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotStressIndexChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId];
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: chartTitle }];
        const layout = {
            title: chartTitle, xaxis: { title: '日期' }, yaxis: { title: '指數 (0-100)', range: [0, 100] },
            shapes: [
                { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 60, x1: 1, y1: 80, fillcolor: 'rgba(255, 255, 0, 0.2)', layer: 'below', line: {width: 0}},
                { type: 'rect', xref: 'paper', yref: 'y', x0: 0, y0: 80, x1: 1, y1: 100, fillcolor: 'rgba(255, 0, 0, 0.2)', layer: 'below', line: {width: 0}}
            ],
            annotations: [
                { xref: 'paper', yref: 'y', x: 0.98, y: 70, text: '高壓力區', showarrow: false, font: { color: 'orange' } },
                { xref: 'paper', yref: 'y', x: 0.98, y: 90, text: '極端壓力區', showarrow: false, font: { color: 'red' } }
            ],
            margin: { l: 60, r: 40, t: 60, b: 60 }, template: 'plotly_white', showlegend: false
        };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotSpreadChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId];
        const traces = [{ x: data.map(d => d.date), y: data.map(d => d.spread_10y2y * 100), type: 'scatter', mode: 'lines', name: '利差' }];
        const layout = { title: chartTitle, xaxis: { title: '日期' }, yaxis: { title: '基點 (BPS)' }, shapes: [{ type: 'line', xref: 'paper', yref: 'y', x0: 0, y0: 0, x1: 1, y1: 0, line: { color: 'grey', dash: 'dash' }}], margin: { l: 60, r: 40, t: 60, b: 60 }, template: 'plotly_white', showlegend: false };
        return Plotly.newPlot(container, traces, layout, { responsive: true });
    }

    function plotMacdChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId];
        const dates = data.map(d => d.date);
        const macdHist = data.map(d => d.macd_hist);
        const plotData = [
            { x: dates, y: data.map(d => d.macd_line), type: 'scatter', mode: 'lines', name: 'MACD 線', yaxis: 'y2' },
            { x: dates, y: data.map(d => d.macd_signal_line), type: 'scatter', mode: 'lines', name: '訊號線', yaxis: 'y2' },
            { x: dates, y: macdHist, type: 'bar', name: 'MACD 柱', yaxis: 'y2', marker: { color: macdHist.map(v => v >= 0 ? 'rgba(214, 48, 49, 0.7)' : 'rgba(0, 184, 148, 0.7)') } },
            { x: dates, y: data.map(d => d.dealer_stress_index), type: 'scatter', mode: 'lines', name: '壓力指數', yaxis: 'y1' }
        ];
        const layout = { title: chartTitle, xaxis: { title: '日期' }, yaxis: { title: '壓力指數', side: 'left' }, yaxis2: { title: 'MACD', overlaying: 'y', side: 'right', showgrid: false }, legend: { x: 0, y: 1.15, orientation: 'h' }, margin: { l: 50, r: 50, t: 80, b: 50 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    function plotRankingBarChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId];
        const latestData = data[data.length - 1];
        const positions = { "淨部位": latestData.dealer_net_positions, "長天期": latestData.dealer_long_term_positions, "短天期": latestData.dealer_short_term_positions };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const plotData = [{ x: sortedPositions.map(([,v]) => v ? v / 1000 : 0), y: sortedPositions.map(([k,]) => k), type: 'bar', orientation: 'h', text: sortedPositions.map(([,v]) => v ? (v/1000).toFixed(2) : "N/A"), textposition: 'inside' }];
        const layout = { title: chartTitle, xaxis: { title: '金額 (十億美元)' }, yaxis: { title: '部位類型' }, margin: { l: 80, r: 40, t: 60, b: 60 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    function plotChangeRankingBarChart(container, data, indicatorId) {
        const chartTitle = titleMapping[indicatorId];
        if (data.length < 2) { container.innerHTML = '<div class="placeholder">數據不足，無法計算變動</div>'; return; }
        const latest = data[data.length - 1];
        const previous = data[data.length - 2];
        const positions = { "淨部位": (latest.dealer_net_positions - previous.dealer_net_positions), "長天期": (latest.dealer_long_term_positions - previous.dealer_long_term_positions), "短天期": (latest.dealer_short_term_positions - previous.dealer_short_term_positions) };
        const sortedPositions = Object.entries(positions).sort(([,a],[,b]) => a-b);
        const values = sortedPositions.map(([,v]) => v ? v / 1000 : 0);
        const plotData = [{ x: values, y: sortedPositions.map(([k,]) => k), type: 'bar', orientation: 'h', text: values.map(v => v.toFixed(2)), textposition: 'inside', marker: { color: values.map(v => v >= 0 ? '#2ca02c' : '#d62728') } }];
        const layout = { title: chartTitle, xaxis: { title: '變動金額 (十億美元)' }, yaxis: { title: '部位類型' }, margin: { l: 80, r: 40, t: 60, b: 60 }, template: 'plotly_white' };
        return Plotly.newPlot(container, plotData, layout, { responsive: true });
    }

    // --- 初始化 ---
    loadInteractiveChart();

});