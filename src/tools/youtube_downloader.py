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
        "--quiet",  # 使用 --quiet 取代 --verbose，減少不必要的日誌輸出
        # "--restrict-filenames", # 移除此選項以支援非 ASCII 字元檔名
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

        # -- 檔案路徑處理邏輯修正 --
        # 舊方法 (_filename) 在音訊轉檔後會指向已被刪除的原始檔，不可靠。
        # 新方法：從 `requested_downloads` 陣列中獲取最終檔案的路徑。
        # 這個陣列記錄了所有下載步驟，最後一個通常是我們想要的最終檔案。
        if video_info.get("requested_downloads") and len(video_info["requested_downloads"]) > 0:
            final_filepath_str = video_info["requested_downloads"][-1].get("filepath")
        else:
            # 作為備用，如果 requested_downloads 不存在，嘗試回退到 _filename
            final_filepath_str = video_info.get('_filename')

        if not final_filepath_str:
            raise RuntimeError("yt-dlp 的 JSON 輸出中未提供有效的檔案路徑。")

        original_path = Path(final_filepath_str)

        # 如果檔案不存在，這是一個嚴重的問題，直接報錯
        if not original_path.exists():
            log.error(f"下載後找不到預期的檔案: {original_path}")
            raise FileNotFoundError(f"yt-dlp 聲稱已下載完成，但找不到檔案: {original_path}")

        # 現在我們手動加上標籤並重新命名檔案
        new_filename = f"{tag}{original_path.stem}{final_suffix}"
        final_path = original_path.with_name(new_filename)

        # 執行重新命名
        original_path.rename(final_path)
        log.info(f"檔案已成功重新命名為: {final_path}")

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