# -*- coding: utf-8 -*-
"""
通用檔案下載器模組 v4 (Final Refactored)
==========================================

本模組提供一個名為 `download_file` 的多功能函式，旨在處理來自各種常見網路來源的檔案下載需求。
此最終版本採用了最穩健的架構，優先根據 URL 特徵選擇專用下載路徑，最後才使用通用方法。

核心功能:
- **來源優先判斷**: 直接分析原始 URL，為 Google Drive, Dropbox, OneDrive 等啟用專用下載邏輯。
- **智慧型別偵測**: 使用 `filetype` 函式庫，確保副檔名正確。
- **安全檔名策略**: 強制使用 ASCII 字元，避免環境錯誤。
- **自動解壓縮**: 若偵測到 ZIP 檔案，會自動解壓縮至子目錄。

主要函式:
    download_file(url: str, download_dir: str) -> tuple[bool, str, str]
"""
import requests
import gdown
import os
import re
import tempfile
import filetype
import zipfile
import uuid
import base64
from urllib.parse import urlparse, unquote

def _post_process_and_unzip(temp_filepath: str, download_dir: str, filename_hint: str) -> tuple[str, str]:
    """
    內部輔助函式：對已下載的臨時檔案進行後處理（偵測類型、命名、解壓縮）。
    """
    try:
        kind = filetype.guess(temp_filepath)
        ext = f".{kind.extension}" if kind else ".dat"

        base_name = os.path.splitext(filename_hint)[0]
        if not base_name:
            base_name = f"download_{uuid.uuid4().hex[:8]}"
        filename = f"{base_name}{ext}"

        filename = re.sub(r'[\\/*?:"<>|]', "_", filename)
        try:
            filename.encode('ascii')
        except UnicodeEncodeError:
            print(f"  [警告] 偵測到非 ASCII 檔名 '{filename}'。將其替換。")
            filename = f"unicode_fallback_{uuid.uuid4().hex[:12]}{ext}"

        if kind and kind.mime == 'application/zip':
            print(f"  [資訊] 偵測到 ZIP 檔案，將自動解壓縮。")
            unzip_dir = os.path.join(download_dir, os.path.splitext(filename)[0])
            os.makedirs(unzip_dir, exist_ok=True)
            with zipfile.ZipFile(temp_filepath, 'r') as zip_ref:
                zip_ref.extractall(unzip_dir)
            return unzip_dir, 'directory'
        else:
            final_path = os.path.join(download_dir, filename)
            os.rename(temp_filepath, final_path)
            return final_path, 'file'
    finally:
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)

def download_file(url: str, download_dir: str) -> tuple[bool, str, str]:
    """
    通用檔案下載器 v4。

    Returns:
        tuple[bool, str, str]: (是否成功, 最終路徑, 產出類型 'file'/'directory' 或 錯誤訊息)
    """
    try:
        os.makedirs(download_dir, exist_ok=True)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}

        # --- 策略一：針對 Google Drive ---
        if 'drive.google.com' in url:
            if '/drive/folders/' in url:
                return False, "Google Drive 資料夾不支援直接下載，請提供單一檔案的連結。", "error"

            temp_gdown_path = None
            try:
                # gdown 下載的檔案名可能包含 unicode，先下載到一個臨時檔
                temp_gdown_path = gdown.download(url, output=f"{os.path.join(download_dir, uuid.uuid4().hex)}.tmp", fuzzy=True, quiet=True)
                if temp_gdown_path is None:
                    return False, "gdown 下載失敗，請檢查 URL 或權限。", "error"

                # 從 gdown 的輸出中獲取原始檔名提示
                # gdown v4+ returns a list, v3 returns a string
                actual_path = temp_gdown_path[0] if isinstance(temp_gdown_path, list) else temp_gdown_path
                filename_hint = os.path.basename(actual_path)

                # 交給統一的後處理函式
                final_path, file_type = _post_process_and_unzip(actual_path, download_dir, filename_hint)
                return True, final_path, file_type
            except Exception as e:
                if temp_gdown_path and os.path.exists(temp_gdown_path):
                    os.remove(temp_gdown_path)
                return False, f"處理 Google Drive 連結時出錯: {e}", "error"

        # --- 策略二：針對其他已知服務或通用下載 ---
        final_url = url
        if 'dropbox.com' in url:
            final_url = url.replace('www.dropbox.com', 'dl.dropboxusercontent.com').replace('?dl=0', '')
            if 'dl=1' not in final_url:
                 final_url += '?dl=1'
        elif '1drv.ms' in url:
            # 對於 OneDrive 短連結，需要先解析出最終的 onedrive.live.com URL
            response = requests.head(url, allow_redirects=True, headers=headers, timeout=20)
            live_url = response.url
            encoded_url = base64.urlsafe_b64encode(live_url.encode()).decode()
            final_url = f"https://api.onedrive.com/v1.0/shares/u!{encoded_url}/root/content"

        # 對於所有非 Google Drive 的連結（包括已轉換的 Dropbox/OneDrive 和短網址）
        with tempfile.NamedTemporaryFile(delete=False, dir=download_dir, suffix='.tmp') as temp_f:
            temp_filepath = temp_f.name
            try:
                with requests.get(final_url, stream=True, headers=headers, timeout=60, allow_redirects=True) as r:
                    r.raise_for_status()
                    content_disposition = r.headers.get('content-disposition')
                    for chunk in r.iter_content(chunk_size=8192):
                        temp_f.write(chunk)

                filename_hint = ""
                if content_disposition:
                    fname_match = re.search(r"filename\*=UTF-8''([^']+)$", content_disposition)
                    if fname_match: filename_hint = unquote(fname_match.group(1))
                    else:
                        fname_match = re.search(r'filename="?([^"]+)"?', content_disposition)
                        if fname_match: filename_hint = unquote(fname_match.group(1).strip('"'))
                if not filename_hint:
                    # 如果請求跟隨了重定向，r.url 是最終的 URL
                    final_redirected_url = r.url if 'r' in locals() and hasattr(r, 'url') else final_url
                    filename_hint = unquote(os.path.basename(urlparse(final_redirected_url).path))

                final_path, file_type = _post_process_and_unzip(temp_filepath, download_dir, filename_hint)
                return True, final_path, file_type
            except Exception as e:
                # 確保在任何錯誤下都能清理臨時檔案
                if os.path.exists(temp_filepath):
                    os.remove(temp_filepath)
                raise e

    except Exception as e:
        return False, f"下載過程中發生未知錯誤: {e}", "error"