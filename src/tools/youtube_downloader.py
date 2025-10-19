# tools/youtube_downloader.py
import argparse
import json
import logging
import sys
import subprocess
import re  # 導入 re 模組
from pathlib import Path

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
log = logging.getLogger('youtube_downloader_tool')

def sanitize_filename(filename: str) -> str:
    """
    清理檔名，以確保其在各種檔案系統中的相容性和安全性。
    - 移除大多數特殊字元。
    - 將空格替換為底線。
    - 保留中日韓文、英文、數字、底線、連字號和點。
    """
    # 移除 URL 中的協議部分，以防意外傳入 URL
    filename = re.sub(r'https?://.*', '', filename)

    # 定義一個包含所有不安全字元和空白字元的正規表示式模式。
    # \s 匹配任何空白字元（空格、tab、換行等）。
    # 其餘部分匹配所有之前定義的不安全特殊字元。
    # `+` 表示匹配一個或多個連續的此類字元。
    SEPARATOR_PATTERN = r'[\s\\/:*?"<>|&%$!@#^()\[\]{}【】！]+'

    # 將一個或多個連續的分隔符直接替換為單一的底線
    filename = re.sub(SEPARATOR_PATTERN, '_', filename)

    # 避免檔名以 '.' 或 '_' 開頭，這在某些系統中可能是隱藏檔案
    filename = filename.lstrip('._')

    # 限制檔名長度（許多檔案系統的限制是 255 個位元組，此處保守取 180）
    if len(filename.encode('utf-8')) > 180:
        # 採用從後方截斷的方式，以保留檔名開頭的辨識度
        while len(filename.encode('utf-8')) > 180:
            filename = filename[:-1]

    # 如果清理後檔名變為空，提供一個預設名稱
    if not filename:
        return "downloaded_media"

    # 移除可能在字串开头或结尾产生的底线
    return filename.strip('_')


def _execute_yt_dlp_command(command: list) -> dict:
    """
    執行一個 yt-dlp 命令並處理其輸出。
    成功時返回解析後的 JSON 物件。
    失敗時拋出 subprocess.CalledProcessError。
    """
    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True, # 如果返回碼非零，則會拋出 CalledProcessError
        encoding='utf-8'
    )
    # yt-dlp 在成功時會將 JSON 輸出到 stdout
    return json.loads(result.stdout)


def download_media(
    youtube_url: str,
    output_dir: Path,
    download_type: str = "audio",
    audio_format: str = "m4a",
    video_resolution: str = "best",
    custom_filename: str | None = None,
    cookies_file: str | None = None,
    raise_exceptions: bool = False
):
    """
    使用 yt-dlp 從 URL 下載媒體（採用兩階段策略以確保檔名正確）。
    1.  第一階段：僅獲取媒體元數據（如標題）。
    2.  第二階段：使用元數據建構最終檔名，並指示 yt-dlp 直接下載到該路徑。
    此方法同時整合了音訊下載的智慧備援機制。
    """
    log.info(f"開始處理媒體。類型: {download_type}, URL: {youtube_url}")

    try:
        # --- 第一階段：僅獲取元數據 ---
        log.info("階段 1/2: 正在獲取媒體元數據...")
        info_command = [
            sys.executable, "-m", "yt_dlp",
            "--print-json", "--quiet", "--skip-download",
            youtube_url
        ]
        if cookies_file and Path(cookies_file).is_file():
            info_command.extend(["--cookies", cookies_file])

        video_info = _execute_yt_dlp_command(info_command)
        video_title = video_info.get("title", "downloaded_media")

        log.info(f"獲取到影片標題: {video_title}")

        # --- 建構最終檔案路徑 ---
        if download_type == "video":
            final_suffix = ".mp4"
            tag = "[mp4]"
        else: # audio
            final_suffix = f".{audio_format}"
            tag = f"[{audio_format}]"

        sanitized_stem = sanitize_filename(video_title)
        final_filename = f"{tag}{sanitized_stem}{final_suffix}"
        final_path = output_dir / final_filename

        # --- 第二階段：執行實際下載 ---
        log.info(f"階段 2/2: 開始下載媒體到 -> {final_path}")

        # 準備基礎下載指令
        download_base_command = [
            sys.executable, "-m", "yt_dlp",
            "--quiet", "--fragment-retries", "infinite", "--no-part",
            "-o", str(final_path), youtube_url
        ]
        if cookies_file and Path(cookies_file).is_file():
            download_base_command.extend(["--cookies", cookies_file])

        if download_type == "video":
            resolution_filter = ""
            if video_resolution != "best":
                height = video_resolution.replace('p', '')
                if height.isdigit():
                    resolution_filter = f"[height<={height}]"
            video_format_string = f"bestvideo{resolution_filter}[ext=mp4]+bestaudio[ext=m4a]/best{resolution_filter}[ext=mp4]/best"
            download_command = download_base_command + ["-f", video_format_string, "--merge-output-format", "mp4"]
            # 影片下載不回傳 JSON，所以我們用 subprocess.run
            subprocess.run(download_command, check=True, capture_output=True, text=True, encoding='utf-8')

        else: # 音訊下載（含備援邏輯）
            # 主要方案：直接下載音訊
            primary_audio_command = download_base_command + ["-x", "--audio-format", audio_format, "-f", "bestaudio/best"]
            try:
                log.info("音訊下載：執行主要方案...")
                subprocess.run(primary_audio_command, check=True, capture_output=True, text=True, encoding='utf-8')
                log.info("主要方案成功。")
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.strip().lower()
                if any(keyword in error_output for keyword in ["authentication", "login required", "sign in", "403 forbidden"]):
                    log.warning("主要方案失敗，偵測到平台限制。啟動備援方案...")
                    # 備援方案：下載影片再提取音訊
                    fallback_format = "bestvideo[height<=144][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
                    fallback_audio_command = download_base_command + ["-x", "--audio-format", audio_format, "-f", fallback_format, "--merge-output-format", "mp4"]
                    subprocess.run(fallback_audio_command, check=True, capture_output=True, text=True, encoding='utf-8')
                    log.info("備援方案成功。")
                else:
                    raise e # 如果是其他錯誤，則重新拋出

        # --- 統一下載成功後的回報 ---
        if not final_path.exists():
            raise FileNotFoundError(f"下載完成後，在預期路徑找不到檔案: {final_path}")

        final_result = {
            "type": "result", "status": "已完成",
            "output_path": str(final_path),
            "video_title": video_title,
            "duration_seconds": video_info.get("duration", 0)
        }
        print(json.dumps(final_result), flush=True)
        log.info(f"✅ 媒體已成功下載並儲存於: {final_path}")

    except subprocess.CalledProcessError as e:
        error_output = e.stderr.strip()
        log.error(f"❌ yt-dlp 執行失敗。返回碼: {e.returncode}\nStderr: {error_output}")
        if raise_exceptions: raise e

        error_code = "GENERAL_ERROR"
        if any(keyword in error_output.lower() for keyword in ["authentication", "login required", "sign in"]):
            error_code = "AUTH_REQUIRED"

        error_payload = {
            "type": "result", "status": "failed",
            "error": error_output, "error_code": error_code
        }
        print(json.dumps(error_payload), flush=True)
        sys.exit(1)

    except Exception as e:
        log.error(f"❌ 下載過程中發生未預期的錯誤: {e}", exc_info=True)
        if raise_exceptions: raise e
        print(json.dumps({"type": "result", "status": "failed", "error": str(e)}), flush=True)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="媒體下載工具 (使用 yt-dlp)。")
    parser.add_argument("--url", type=str, required=True)
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--download-type", type=str, default="audio", choices=['audio', 'video'])
    parser.add_argument("--audio-format", type=str, default="m4a")
    parser.add_argument("--video-resolution", type=str, default="best")
    # custom-filename 暫時不從 main 函式中直接使用，因為新的邏輯是基於 title
    # parser.add_argument("--custom-filename", type=str, default=None)
    parser.add_argument("--cookies-file", type=str, default=None)

    args = parser.parse_args()

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    download_media(
        args.url,
        output_path,
        args.download_type,
        args.audio_format,
        args.video_resolution,
        None, # custom_filename 設為 None
        args.cookies_file
    )

if __name__ == "__main__":
    main()