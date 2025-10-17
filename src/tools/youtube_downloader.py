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

    # 決定最終的檔案副檔名和檔名標籤
    if download_type == "video":
        final_suffix = ".mp4"
        tag = "[mp4]"
    else: # audio
        final_suffix = f".{audio_format}"
        tag = f"[{audio_format}]"

    # 建立一個基礎的檔名模板，稍後會在其前面加上標籤
    base_output_template = f"%(title)s"

    command = [
        sys.executable, "-m", "yt_dlp",
        "--print-json",
        "--verbose",
        "--restrict-filenames",
        "--fragment-retries", "infinite",
        "--no-part",
    ]

    if download_type == "audio":
        command.extend(["-x", "--audio-format", audio_format])
        command.extend(["-f", "bestaudio/best"])
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

    # 我們先不指定完整的輸出路徑，讓 yt-dlp 使用預設的標題
    # 這樣可以避免因自訂檔名導致的潛在問題
    command.extend(["-o", f"{output_dir / base_output_template}.%(ext)s", youtube_url])

    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
        video_info = json.loads(result.stdout)

        # 從 yt-dlp 的輸出中獲取它實際使用的檔案路徑
        original_filepath_str = video_info.get('_filename')
        if not original_filepath_str:
            raise RuntimeError("yt-dlp did not provide the output filename in its JSON.")

        original_path = Path(original_filepath_str)

        # 現在我們手動加上標籤並重新命名檔案
        new_filename = f"{tag}{original_path.stem}{final_suffix}"
        final_path = original_path.with_name(new_filename)

        if original_path.exists():
            original_path.rename(final_path)
            log.info(f"檔案已成功重新命名為: {final_path}")
        else:
            log.warning(f"找不到原始下載檔案 {original_path}，無法重新命名。")
            # 作為備用，嘗試直接尋找已命名的檔案
            if not final_path.exists():
                 raise FileNotFoundError(f"找不到原始檔案或已重新命名的檔案。")

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