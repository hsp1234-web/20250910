// src/static/js/page_bond.js

document.addEventListener('DOMContentLoaded', () => {
    console.log("簡化版債券分析頁面腳本已載入 (v2 - 金鑰檢查)。");

    const indicators = ['gdp', 'cpi', 'fedfunds', 'ism'];
    const statusDiv = document.getElementById('update-status');

    async function checkFredKeyAndInitialize() {
        try {
            const response = await fetch('/api/key_status/fred');
            if (!response.ok) {
                throw new Error(`伺服器回應錯誤: ${response.status}`);
            }
            const keyStatus = await response.json();

            if (keyStatus.available) {
                console.log("✅ FRED API 金鑰可用，正在啟用圖表功能。");
                statusDiv.textContent = "FRED API 金鑰已就緒，請選擇一個指標以生成圖表。";
                initializeButtons(true); // 啟用按鈕
            } else {
                console.warn("FRED API 金鑰不可用，圖表功能將被禁用。");
                statusDiv.textContent = "❌ 後端 FRED API 金鑰尚未設定，圖表功能已禁用。";
                initializeButtons(false); // 禁用按鈕
            }
        } catch (error) {
            console.error("檢查 FRED 金鑰狀態時發生錯誤:", error);
            statusDiv.textContent = "❌ 無法檢查金鑰狀態，圖表功能已禁用。請檢查網路連線或後端服務。";
            initializeButtons(false); // 發生錯誤時也禁用按鈕
        }
    }

    function initializeButtons(enabled) {
        indicators.forEach(id => {
            const button = document.getElementById(`btn-fetch-${id}`);
            if (button) {
                // 無論如何，'ism' 按鈕目前都是禁用的
                if (id === 'ism') {
                    button.disabled = true;
                    return;
                }

                button.disabled = !enabled;
                if (enabled) {
                    button.addEventListener('click', () => updateChart(id));
                }
            }
        });
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

    // 啟動頁面初始化流程
    checkFredKeyAndInitialize();
});
