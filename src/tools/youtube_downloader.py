# tools/youtube_downloader.py
import argparse
import json
import logging
import sys
import subprocess
from pathlib import Path

# --- 日誌設定 ---
# Log to stderr so that stdout can be used for JSON output
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
    custom_filename: str | None = None,
    cookies_file: str | None = None
):
    """
    使用 yt-dlp 從 YouTube URL 下載媒體（音訊或影片）。

    :param youtube_url: 要下載的 YouTube URL。
    :param output_dir: 儲存檔案的目錄。
    :param download_type: 'audio' 或 'video'。
    :param custom_filename: 自訂的檔案名稱 (不含副檔名)。
    :param cookies_file: 用於驗證的 cookies.txt 檔案路徑。
    """
    log.info(f"開始下載媒體，類型: {download_type}，URL: {youtube_url}")

    output_template = f"{str(output_dir / custom_filename)}.%(ext)s" if custom_filename else f"{str(output_dir / '%(title)s')}.%(ext)s"
    final_suffix = ".mp3" if download_type == "audio" else ".mp4"

    # JULES DEBUG (2025-08-31): 根據最新分析報告，此處是修復環境依賴問題的關鍵。
    # 雖然 `python -m yt_dlp` 在理論上更具可攜性，但使用者的報告明確指出要直接呼叫 `yt-dlp`。
    # 為了完全遵循修復建議，我們將呼叫方式改回直接呼叫執行檔，讓作業系統從 PATH 中尋找。
    command = ["yt-dlp", "--print-json"]

    if download_type == "audio":
        command.extend([
            "-f", "bestaudio",
            "-x",  # --extract-audio
            "--audio-format", "mp3",
        ])
    else: # video
        command.extend([
            "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
        ])

    # 如果提供了 cookies 檔案路徑，則加入指令
    if cookies_file and Path(cookies_file).is_file():
        log.info(f"使用 Cookies 檔案: {cookies_file}")
        command.extend(["--cookies", cookies_file])

    command.extend(["-o", output_template, youtube_url])

    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8'
        )

        video_info = json.loads(result.stdout)
        final_filepath_str = video_info.get('_filename')

        if not final_filepath_str:
            log.error("無法從 yt-dlp 的輸出中確定檔案名稱。")
            raise RuntimeError("yt-dlp did not provide the output filename in its JSON.")

        # yt-dlp 可能會回傳轉檔前的副檔名，我們強制使用我們期望的副檔名
        final_path = Path(final_filepath_str).with_suffix(final_suffix)

        # 在某些情況下，合併後的檔案名稱可能與 yt-dlp 報告的 _filename 不同，
        # 例如，當它從 .mkv 轉換為 .mp4 時。我們需要找到實際的檔案。
        if not final_path.exists():
            # 建立一個預期的路徑（基於標題或自訂名稱）
            expected_base = custom_filename or video_info.get("title", "unknown")
            # yt-dlp 會清理檔名，我們這裡做一個簡化版的模擬
            sanitized_base = "".join(c for c in expected_base if c.isalnum() or c in (' ', '_', '-')).rstrip()
            expected_path = output_dir / f"{sanitized_base}{final_suffix}"

            if expected_path.exists():
                final_path = expected_path
            else:
                log.warning(f"找不到預期的檔案 {final_path} 或 {expected_path}。將搜尋目錄...")
                # 在輸出目錄中搜尋最新的、符合副檔名的檔案作為最後手段
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
        log.error(f"❌ yt-dlp 執行失敗。返回碼: {e.returncode}")
        log.error(f"Stderr: {e.stderr}")

        # 增強錯誤偵測
        error_message = e.stderr
        error_code = None
        if "authentication" in error_message.lower() or "login required" in error_message.lower():
            error_code = "AUTH_REQUIRED"
            error_message = "此影片需要登入驗證。請提供 cookies.txt 檔案。"

        error_result = {"type": "result", "status": "failed", "error": error_message, "error_code": error_code}
        print(json.dumps(error_result), flush=True)
        sys.exit(1)
    except Exception as e:
        log.error(f"❌ 下載過程中發生未預期的錯誤: {e}", exc_info=True)
        error_result = {"type": "result", "status": "failed", "error": str(e)}
        print(json.dumps(error_result), flush=True)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="YouTube 媒體下載工具 (使用 yt-dlp)。")
    parser.add_argument("--url", type=str, required=True, help="YouTube URL。")
    parser.add_argument("--output-dir", type=str, required=True, help="儲存媒體的目錄。")
    parser.add_argument("--download-type", type=str, default="audio", choices=['audio', 'video'], help="下載類型：'audio' 或 'video'。")
    parser.add_argument("--custom-filename", type=str, default=None, help="自訂的檔案名稱 (不含副檔名)。")
    parser.add_argument("--cookies-file", type=str, default=None, help="用於驗證的 cookies.txt 檔案路徑。")

    args = parser.parse_args()

    output_path = Path(args.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    download_media(
        args.url,
        output_path,
        args.download_type,
        args.custom_filename,
        args.cookies_file
    )

if __name__ == "__main__":
    main()
