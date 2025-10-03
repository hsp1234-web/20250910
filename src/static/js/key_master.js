// src/static/js/key_master.js

document.addEventListener('DOMContentLoaded', () => {
    const keyListContainer = document.getElementById('key-list-container');
    // 我們之前建立的 key_master_service 的位址
    const apiKeyServiceUrl = 'http://127.0.0.1:8008/api/v1/keys';

    const renderKeys = (keys) => {
        // 如果沒有金鑰，顯示提示訊息
        if (!keys || keys.length === 0) {
            keyListContainer.innerHTML = '<p class="no-keys-message">目前沒有任何由 Key Master Service 管理的金鑰。</p>';
            return;
        }

        // 開始建立表格 HTML
        let tableHtml = '<table class="key-table">';
        tableHtml += `
            <thead>
                <tr>
                    <th>金鑰名稱</th>
                    <th>類型</th>
                    <th>雜湊值 (末8碼)</th>
                    <th>狀態</th>
                    <th>上次驗證時間</th>
                </tr>
            </thead>
            <tbody>
        `;

        // 遍歷金鑰資料，為每一筆資料建立一個表格行
        keys.forEach(key => {
            const statusClass = key.is_valid ? 'status-valid' : 'status-invalid';
            const statusText = key.is_valid ? '有效' : '無效';
            const lastValidated = key.last_validated_at
                ? new Date(key.last_validated_at).toLocaleString('zh-TW')
                : '從未';

            tableHtml += `
                <tr>
                    <td>${key.key_name}</td>
                    <td>${key.key_type}</td>
                    <td>...${key.key_hash.slice(-8)}</td>
                    <td class="${statusClass}">${statusText}</td>
                    <td>${lastValidated}</td>
                </tr>
            `;
        });

        tableHtml += '</tbody></table>';

        // 將產生的表格 HTML 插入到容器中
        keyListContainer.innerHTML = tableHtml;
    };

    const fetchAndRenderKeys = async () => {
        try {
            const response = await fetch(apiKeyServiceUrl);

            // 如果請求失敗 (例如服務未啟動)
            if (!response.ok) {
                throw new Error(`無法連接到金鑰服務 (HTTP ${response.status})，請確認服務是否已在 http://127.0.0.1:8008 正常運行。`);
            }

            const keys = await response.json();
            renderKeys(keys);

        } catch (error) {
            console.error('獲取金鑰時發生錯誤:', error);
            // 在頁面上顯示錯誤訊息，方便除錯
            keyListContainer.innerHTML = `<p class="no-keys-message" style="color: var(--phoenix-danger-color);">${error.message}</p>`;
        }
    };

    // 頁面載入後，立即執行獲取和渲染金鑰的函式
    fetchAndRenderKeys();
});