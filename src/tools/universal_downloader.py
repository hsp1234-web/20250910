import requests
import gdown
import os
import re
import logging
from urllib.parse import urlparse
from pathlib import Path

log = logging.getLogger(__name__)

class UniversalDownloader:
    """
    一個通用的檔案下載器，可以處理來自不同來源的 URL，
    包括短網址、Google Drive、Dropbox 和直接連結。
    """

    def __init__(self, output_dir: str = "downloads"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"通用下載器已初始化，下載目錄設定為: {self.output_dir}")

    def download(self, url: str) -> Path | None:
        """
        主下載方法。接收一個 URL，嘗試下載檔案，並在成功時回傳檔案路徑。

        :param url: 要下載的檔案 URL。
        :return: 成功時回傳下載檔案的 Path 物件，失敗時回傳 None。
        """
        log.info(f"📥 開始處理 URL: {url}")
        try:
            final_url = self._get_final_url(url)
            log.info(f"    - URL 已解析為: {final_url}")

            parsed_url = urlparse(final_url)
            hostname = parsed_url.hostname.lower() if parsed_url.hostname else ""

            if "drive.google.com" in hostname:
                return self._download_from_gdrive(final_url)
            elif "dropbox.com" in hostname:
                return self._download_from_dropbox(final_url)
            elif "1drv.ms" in hostname or "onedrive.live.com" in hostname:
                return self._download_from_onedrive(final_url)
            else:
                return self._download_direct(final_url)

        except Exception as e:
            log.error(f"❌ 處理 URL '{url}' 時發生未預期的錯誤: {e}", exc_info=True)
            return None

    def _get_final_url(self, url: str) -> str:
        """跟隨重定向，獲取最終的 URL。"""
        try:
            response = requests.head(url, allow_redirects=True, timeout=15)
            response.raise_for_status()
            return response.url
        except requests.RequestException as e:
            log.warning(f"解析短網址時發生錯誤: {e}。將嘗試使用原始 URL。")
            return url

    def _download_from_gdrive(self, url: str) -> Path | None:
        """使用 gdown 處理 Google Drive 連結。"""
        log.info("    - 策略: Google Drive")
        # gdown 可以自動生成檔案名稱，但為了統一管理，我們指定一個
        output_path = self.output_dir / f"gdrive_{Path(urlparse(url).path).name}.tmp"
        gdown.download(url, output=str(output_path), quiet=False, fuzzy=True)
        # gdown 下載後，我們可能需要根據實際情況重新命名
        # 這裡為了簡單起見，直接回傳路徑
        if output_path.exists():
            log.info(f"✔️ Google Drive 檔案下載成功: {output_path}")
            return output_path
        return None

    def _download_from_dropbox(self, url: str) -> Path | None:
        """處理 Dropbox 連結。"""
        log.info("    - 策略: Dropbox")
        # 將 ?dl=0 替換為 ?dl=1
        if "?dl=0" in url:
            direct_url = url.replace("?dl=0", "?dl=1")
        elif url.endswith("?dl=0"):
             direct_url = url[:-1] + "1"
        else:
            direct_url = url + ("&dl=1" if "?" in url else "?dl=1")

        log.info(f"    - 轉換後的直接下載連結: {direct_url}")
        return self._download_direct(direct_url, source="dropbox")

    def _download_from_onedrive(self, url: str) -> Path | None:
        """處理 OneDrive 連結。PoC 發現直接請求通常有效。"""
        log.info("    - 策略: OneDrive")
        # PoC 顯示 requests 的自動重定向對 OneDrive 很有效
        # 我們可能需要處理 'embed' -> 'download' 的情況作為備案
        if "embed" in url:
            direct_url = url.replace("embed", "download")
            log.info(f"    - 偵測到 'embed'，轉換為下載連結: {direct_url}")
            return self._download_direct(direct_url, source="onedrive")

        return self._download_direct(url, source="onedrive")

    def _download_direct(self, url: str, source: str = "direct") -> Path | None:
        """通用的直接下載方法。"""
        response = requests.get(url, allow_redirects=True, timeout=30)
        response.raise_for_status()

        # 從 headers 中獲取檔案名稱
        content_disposition = response.headers.get('content-disposition')
        filename = None
        if content_disposition:
            match = re.search(r'filename="(.+?)"', content_disposition)
            if match:
                filename = match.group(1)

        if not filename:
            # 如果 headers 中沒有，則從 URL 中猜測
            filename = os.path.basename(urlparse(url).path)
            if not filename: # 如果 URL 以 / 結尾
                filename = f"{source}_file_{int(time.time())}.tmp"

        output_path = self.output_dir / filename
        with open(output_path, 'wb') as f:
            f.write(response.content)

        log.info(f"✔️ 直接下載成功: {output_path} ({output_path.stat().st_size / 1024:.2f} KB)")
        return output_path
