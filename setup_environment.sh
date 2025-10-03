#!/bin/bash
#
# 環境自動化設定腳本
#
# 這個腳本會安裝所有必要的系統級和 Python 依賴，
# 以便在本機或新的開發環境中，快速地設定好執行本專案所需的一切。
#
# 使用方法:
# 1. 確保您在一個基於 Debian/Ubuntu 的系統中。
# 2. 從專案根目錄執行此腳本: ./setup_environment.sh
#

# --- 腳本設定 ---
# 如果任何指令失敗，立即終止腳本
set -e

echo "=== [1/5] 更新系統套件列表 ==="
sudo apt-get update -y

echo ""
echo "=== [2/5] 安裝系統級核心依賴 (Chrome & npm) ==="
# 安裝 wget 和 gnupg，這是處理軟體源的必要工具
sudo apt-get install -y wget gnupg

# 新增 Google Chrome 的官方軟體源
# 檢查軟體源是否已存在，避免重複新增
if ! grep -q "dl.google.com/linux/chrome/deb" /etc/apt/sources.list.d/google-chrome.list; then
  echo "新增 Google Chrome 軟體源..."
  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
  sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
  sudo apt-get update -y
else
  echo "Google Chrome 軟體源已存在，跳過新增步驟。"
fi

# 安裝 Chrome 瀏覽器和 Node.js 套件管理器
sudo apt-get install -y google-chrome-stable npm

echo ""
echo "=== [3/5] 安裝 Playwright 所需的系統依賴 ==="
# 使用 Playwright 的內建工具來安裝所有瀏覽器核心所需的函式庫
# 這會自動處理數百個圖形和多媒體相關的依賴
playwright install-deps

echo ""
echo "=== [4/5] 安裝所有 Python 套件 ==="
# 使用 uv 來高效地從 requirements.txt 總表中安裝所有 Python 依賴
# --system 參數會將其安裝到系統的 Python 環境中，以匹配我們的執行方式
uv pip install -r requirements.txt --system

echo ""
echo "=== [5/5] 設定 Playwright 瀏覽器核心 ==="
# 最後，執行 playwright install 來下載和設定瀏覽器核心
playwright install

echo ""
echo "✅✅✅ 環境設定完成！您的系統現在已經準備好運行專案。 ✅✅✅"