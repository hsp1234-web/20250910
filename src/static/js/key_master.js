// src/static/js/key_master.js (v2 - 動態服務發現版)

document.addEventListener('DOMContentLoaded', () => {
    const keyListContainer = document.getElementById('key-list-container');
    const registryApiUrl = '/api/v1/service-registry';

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
            // --- 第 1 步：從主機獲取服務註冊表 ---
            console.log("正在從主機獲取服務註冊表...");
            const registryResponse = await fetch(registryApiUrl);
            if (!registryResponse.ok) {
                throw new Error(`無法獲取服務註冊表 (HTTP ${registryResponse.status})。主應用程式可能尚未就緒。`);
            }
            const registry = await registryResponse.json();

            // --- 第 2 步：從註冊表中找到 key_master_service 的 URL ---
            const keyMasterInfo = registry['key_master_service'];
            if (!keyMasterInfo || !keyMasterInfo.url) {
                throw new Error("在服務註冊表中找不到 'key_master_service' 的有效位址。");
            }
            const keyServiceUrl = `${keyMasterInfo.url}/api/v1/keys`;
            console.log(`已動態發現 Key Master Service 的 API 端點: ${keyServiceUrl}`);

            // --- 第 3 步：使用動態 URL 獲取金鑰資料 ---
            const keysResponse = await fetch(keyServiceUrl);
            if (!keysResponse.ok) {
                throw new Error(`無法從 Key Master Service (${keyServiceUrl}) 連接金鑰資料 (HTTP ${keysResponse.status})。`);
            }

            const keys = await keysResponse.json();
            renderKeys(keys);

        } catch (error) {
            console.error('獲取金鑰時發生錯誤:', error);
            // 在頁面上顯示詳細的錯誤訊息，方便除錯
            keyListContainer.innerHTML = `<p class="no-keys-message" style="color: var(--phoenix-danger-color); font-weight: bold;">❌ 載入失敗：<br><span style="font-weight: normal;">${error.message}</span></p>`;
        }
    };

    // 頁面載入後，立即執行獲取和渲染金鑰的函式
    fetchAndRenderKeys();
});