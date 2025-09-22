// playwright_test.js

const { chromium } = require('playwright');

(async () => {
  console.log('正在啟動 Playwright...');
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const targetUrl = 'http://127.0.0.1:8001/page3';
  console.log(`正在導覽至 ${targetUrl} ...`);

  try {
    await page.goto(targetUrl, { waitUntil: 'networkidle' });
    console.log('頁面導覽成功。');

    // 等待關鍵元素出現，確保頁面已載入
    console.log('正在等待頁面關鍵元素「待處理的檔案」載入...');
    await page.waitForSelector('h2:has-text("待處理的檔案")', { timeout: 15000 });
    console.log('關鍵元素已載入。');

    // 給予額外時間讓動態內容 (WebSocket) 完成渲染
    await page.waitForTimeout(2000);

    const screenshotPath = 'page3_verification.jpg';
    console.log(`正在截取頁面並儲存至 ${screenshotPath} ...`);
    await page.screenshot({ path: screenshotPath, fullPage: true, type: 'jpeg', quality: 90 });
    console.log(`✅ 截圖成功！檔案已儲存於 ${screenshotPath}`);

  } catch (error) {
    console.error('❌ Playwright 驗證過程中發生錯誤:', error);
    process.exit(1); // 以錯誤碼退出
  } finally {
    await browser.close();
    console.log('Playwright 瀏覽器已關閉。');
  }
})();
