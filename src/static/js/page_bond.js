// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("簡化版債券分析頁面腳本已載入。");

    const indicators = ['gdp', 'cpi', 'fedfunds', 'ism'];
    const statusDiv = document.getElementById('update-status');

    // 為每個指標的按鈕設定事件監聽器
    indicators.forEach(id => {
        const button = document.getElementById(`btn-fetch-${id}`);
        if (button) {
            button.addEventListener('click', () => {
                // ism 按鈕是禁用的，但我們還是為它加上邏輯以備未來使用
                if (button.disabled) {
                    console.log(`按鈕 ${id} 目前被禁用。`);
                    return;
                }
                updateChart(id);
            });
        }
    });

    function updateChart(indicatorId) {
        const imgElement = document.getElementById(`${indicatorId}-chart-img`);
        if (!imgElement) {
            console.error(`找不到 ID 為 ${indicatorId}-chart-img 的圖片元素。`);
            return;
        }

        console.log(`正在為 ${indicatorId} 更新圖表...`);
        statusDiv.textContent = `正在為 ${indicatorId.toUpperCase()} 生成圖表，請稍候...`;

        // 建立 API 端點 URL。
        // 注意：我們假設主伺服器會有一個代理將此請求轉發到 bond_data_service
        // 這樣可以避免在前端處理服務發現和CORS問題。
        const apiUrl = `/api/bond_service/chart/${indicatorId}`;

        // 附加時間戳以避免瀏覽器快取舊圖片
        const finalUrl = `${apiUrl}?t=${new Date().getTime()}`;

        // 先顯示一個載入中的提示
        imgElement.src = ""; // 清空 src 以顯示 alt 文字
        imgElement.alt = "圖表載入中...";

        // 設定圖片載入成功和失敗的事件處理
        imgElement.onload = () => {
            console.log(`${indicatorId} 圖表載入成功。`);
            statusDiv.textContent = `✅ ${indicatorId.toUpperCase()} 圖表已更新。`;
            imgElement.alt = `指標 ${indicatorId} 的圖表`; // 成功後更新 alt
        };

        imgElement.onerror = () => {
            console.error(`${indicatorId} 圖表載入失敗。`);
            statusDiv.textContent = `❌ ${indicatorId.toUpperCase()} 圖表載入失敗。請檢查後端服務日誌。`;
            imgElement.alt = "圖表載入失敗。";
        };

        // 開始載入圖片
        imgElement.src = finalUrl;
    }
});
