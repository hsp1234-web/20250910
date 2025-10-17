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
    使用 yt-dlp 從 URL 下載媒體，支援音訊和影片，以及不同的格式和解析度。
    """
    log.info(f"開始下載媒體。類型: {download_type}, URL: {youtube_url}, 音訊格式: {audio_format}, 影片解析度: {video_resolution}")

    output_template = f"{str(output_dir / custom_filename)}.%(ext)s" if custom_filename else f"{str(output_dir / '%(title)s')}.%(ext)s"

    command = [
        sys.executable, "-m", "yt_dlp",
        "--print-json",
        "--verbose",
        "--restrict-filenames",
        "--fragment-retries", "infinite",
        "--no-part",
    ]

    if download_type == "audio":
        final_suffix = f".{audio_format}"
        command.extend(["-x", "--audio-format", audio_format])
        # 為了獲得最佳音質和最快的速度，我們總是下載最好的音訊源，然後再進行轉檔（如果需要）
        command.extend(["-f", "bestaudio/best"])
    else: # video
        final_suffix = ".mp4"
        # 建立解析度篩選器
        resolution_filter = ""
        if video_resolution != "best":
            # 移除 'p' 並只取數字
            height = video_resolution.replace('p', '')
            if height.isdigit():
                resolution_filter = f"[height<={height}]"

        # 組合格式選擇字串
        video_format_string = f"bestvideo{resolution_filter}[ext=mp4]+bestaudio[ext=m4a]/best{resolution_filter}[ext=mp4]/best"
        command.extend(["-f", video_format_string, "--merge-output-format", "mp4"])

    if cookies_file and Path(cookies_file).is_file():
        log.info(f"使用 Cookies 檔案: {cookies_file}")
        command.extend(["--cookies", cookies_file])

    command.extend(["-o", output_template, youtube_url])
    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        video_info = json.loads(result.stdout)

        # yt-dlp 在 --print-json 模式下，_filename 可能指向原始未轉檔的路徑
        # 我們需要自己建構最終的路徑
        base_name = custom_filename or video_info.get("title", "unknown_file")
        # yt-dlp 會做更複雜的清理，但這是一個合理的近似值
        sanitized_base = "".join(c for c in base_name if c.isalnum() or c in (' ', '_', '-')).rstrip()
        final_path = output_dir / f"{sanitized_base}{final_suffix}"

        # 由於檔名可能不完全匹配，我們在目錄中尋找最新的、符合副檔名的檔案
        if not final_path.exists():
            log.warning(f"找不到預期的檔案 {final_path}。將搜尋目錄...")
            files_in_dir = list(output_dir.glob(f"*{final_suffix}"))
            if files_in_dir:
                latest_file = max(files_in_dir, key=lambda p: p.stat().st_mtime)
                final_path = latest_file
                log.info(f"找到最新的檔案作為下載結果: {final_path}")
            else:
                raise FileNotFoundError(f"在 {output_dir} 中找不到任何 {final_suffix} 檔案。")

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
    parser.add_argument("--custom-filename", type=str, default=None)
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
        args.custom_filename,
        args.cookies_file
    )

if __name__ == "__main__":
    main()