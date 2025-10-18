# tools/youtube_downloader.py
import argparse
import json
import logging
import sys
import subprocess
from pathlib import Path

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
log = logging.getLogger('youtube_downloader_tool')

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
    使用 yt-dlp 從 URL 下載媒體，並直接輸出為帶有格式標籤的檔名。
    """
    log.info(f"開始下載媒體。類型: {download_type}, URL: {youtube_url}, 音訊格式: {audio_format}, 影片解析度: {video_resolution}")

    # 決定檔名標籤
    tag = f"[{audio_format}]" if download_type == "audio" else "[mp4]"

    # 使用 yt-dlp 的輸出模板功能來直接建立最終檔名
    # 我們將標籤和標題組合在一起作為檔名的基礎
    # 注意：yt-dlp 會自動處理特殊字元和空格
    output_template = f"{output_dir / (tag + '%(title)s')}.%(ext)s"

    command = [
        sys.executable, "-m", "yt_dlp",
        "--print-json",
        "--quiet", # (Jules @ 2025-10-18) 徹底抑制非錯誤日誌，解決日誌風暴問題
        # "--restrict-filenames", # (Jules @ 2025-10-18) 移除此參數以支援中文檔名
        "--fragment-retries", "infinite",
        "--no-part",
        "-o", output_template, # 直接指定最終輸出路徑模板
    ]

    if download_type == "audio":
        command.extend(["-x", "--audio-format", audio_format, "-f", "bestaudio/best"])
    else: # video
        resolution_filter = ""
        if video_resolution != "best":
            height = video_resolution.replace('p', '')
            if height.isdigit():
                resolution_filter = f"[height<={height}]"

        video_format_string = f"bestvideo{resolution_filter}[ext=mp4]+bestaudio[ext=m4a]/best{resolution_filter}[ext=mp4]/best"
        command.extend(["-f", video_format_string, "--merge-output-format", "mp4"])

    if cookies_file and Path(cookies_file).is_file():
        log.info(f"使用 Cookies 檔案: {cookies_file}")
        command.extend(["--cookies", cookies_file])

    command.append(youtube_url)
    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        video_info = json.loads(result.stdout)

        # (Jules @ 2025-10-18) 增強修復：
        # 對於某些影片類型（如 YouTube Shorts），'filepath' 和 '_filename' 可能都不存在於頂層 JSON 物件中。
        # 根據 yt-dlp 的行為，最可靠的方式是從 'requested_downloads' 陣列中獲取最終檔案路徑。
        # 這個陣列記錄了所有實際下載和處理過的檔案。
        final_filepath_str = None
        if 'requested_downloads' in video_info and video_info['requested_downloads']:
            # 通常，轉換後的最終檔案會是這個列表中的最後一個
            final_filepath_str = video_info['requested_downloads'][-1].get('filepath')

        # 如果上述方法失敗，則退回至先前的方法作為備用
        if not final_filepath_str:
            final_filepath_str = video_info.get('filepath') or video_info.get('_filename')

        if not final_filepath_str or not Path(final_filepath_str).exists():
            # 增加更詳細的錯誤日誌，以便未來偵錯
            log.error(f"檔案驗證失敗。yt-dlp 回傳的資訊: {json.dumps(video_info, indent=2)}")
            raise FileNotFoundError(f"yt-dlp 處理完成後，無法在指定路徑找到檔案: {final_filepath_str}")

        final_path = Path(final_filepath_str)
        final_result = {
            "type": "result",
            "status": "已完成",
            "output_path": str(final_path),
            "video_title": video_info.get("title", "Unknown Title"),
            "duration_seconds": video_info.get("duration", 0)
        }
        print(json.dumps(final_result), flush=True)
        log.info(f"✅ 媒體下載成功: {final_path}")

    except subprocess.CalledProcessError as e:
        log.error(f"❌ yt-dlp 執行失敗。返回碼: {e.returncode}\nStderr: {e.stderr}")
        if raise_exceptions: raise e
        error_message = e.stderr
        error_code = "GENERAL_ERROR"
        if "authentication" in error_message.lower() or "login required" in error_message.lower():
            error_code = "AUTH_REQUIRED"
            error_message = "此影片需要登入驗證。請提供 cookies.txt 檔案。"
        print(json.dumps({"type": "result", "status": "failed", "error": error_message, "error_code": error_code}), flush=True)
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
        None, # custom_filename is now handled by the template
        args.cookies_file
    )

if __name__ == "__main__":
    main()