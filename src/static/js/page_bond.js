// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("簡化版債券分析頁面腳本 v2 已載入 (整合統一金鑰管理)。");

    const indicators = ['gdp', 'cpi', 'fedfunds', 'ism'];
    const statusDiv = document.getElementById('update-status');

    // 為每個指標的按鈕設定事件監聽器
    indicators.forEach(id => {
        const button = document.getElementById(`btn-fetch-${id}`);
        if (button) {
            button.addEventListener('click', () => {
                if (button.disabled) {
                    console.log(`按鈕 ${id} 目前被禁用。`);
                    return;
                }
                // JULES (2025-09-29): 在更新圖表前，先檢查金鑰狀態
                checkKeyAndupdateChart(id);
            });
        }
    });

    async function checkKeyAndupdateChart(indicatorId) {
        statusDiv.textContent = `正在檢查 FRED API 金鑰狀態...`;
        try {
            const keyResponse = await fetch('/api/keys/status/fred');
            const keyStatus = await keyResponse.json();

            if (keyResponse.ok && keyStatus.available) {
                console.log("✅ FRED API 金鑰已就緒，開始生成圖表。");
                updateChart(indicatorId); // 金鑰可用，繼續執行
            } else {
                throw new Error("尚未設定或驗證有效的 FRED API 金鑰。請至「金鑰管理」頁面新增。");
            }
        } catch (error) {
            console.error("金鑰檢查失敗:", error.message);
            statusDiv.textContent = `❌ 金鑰檢查失敗: ${error.message}`;
            const imgElement = document.getElementById(`${indicatorId}-chart-img`);
            if (imgElement) {
                imgElement.src = "";
                imgElement.alt = `金鑰檢查失敗: ${error.message}`;
            }
        }
    }

    function updateChart(indicatorId) {
        const imgElement = document.getElementById(`${indicatorId}-chart-img`);
        if (!imgElement) {
            console.error(`找不到 ID 為 ${indicatorId}-chart-img 的圖片元素。`);
            return;
        }

        console.log(`正在為 ${indicatorId} 更新圖表...`);
        statusDiv.textContent = `正在為 ${indicatorId.toUpperCase()} 生成圖表，請稍候...`;

        const apiUrl = `/api/bond_service/chart/${indicatorId}`;
        const finalUrl = `${apiUrl}?t=${new Date().getTime()}`;

        imgElement.src = "";
        imgElement.alt = "圖表載入中...";

        imgElement.onload = () => {
            console.log(`${indicatorId} 圖表載入成功。`);
            statusDiv.textContent = `✅ ${indicatorId.toUpperCase()} 圖表已更新。`;
            imgElement.alt = `指標 ${indicatorId} 的圖表`;
        };

        imgElement.onerror = () => {
            console.error(`${indicatorId} 圖表載入失敗。`);
            statusDiv.textContent = `❌ ${indicatorId.toUpperCase()} 圖表載入失敗。請檢查後端服務日誌。`;
            imgElement.alt = "圖表載入失敗。";
        };

        imgElement.src = finalUrl;
    }
});