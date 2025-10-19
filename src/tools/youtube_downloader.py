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
    使用 yt-dlp 從 URL 下載媒體，支援音訊和影片。
    音訊下載具備智慧備援機制：先嘗試直接下載音訊，若因平台限制失敗，
    會自動切換到下載低解析度影片並從中提取音訊的模式。
    """
    log.info(f"開始下載媒體。類型: {download_type}, URL: {youtube_url}")

    # --- 基本指令設定 ---
    base_command = [
        sys.executable, "-m", "yt_dlp",
        "--print-json", "--quiet",
        "--fragment-retries", "infinite",
        "--no-part",
    ]
    if cookies_file and Path(cookies_file).is_file():
        log.info(f"使用 Cookies 檔案: {cookies_file}")
        base_command.extend(["--cookies", cookies_file])

    base_output_template = f"%(title)s"
    output_template = f"{output_dir / base_output_template}.%(ext)s"
    base_command.extend(["-o", output_template, youtube_url])

    video_info = None

    try:
        # --- 根據下載類型準備指令 ---
        if download_type == "video":
            # 影片下載邏輯（單一方案）
            final_suffix = ".mp4"
            tag = "[mp4]"
            resolution_filter = ""
            if video_resolution != "best":
                height = video_resolution.replace('p', '')
                if height.isdigit():
                    resolution_filter = f"[height<={height}]"
            video_format_string = f"bestvideo{resolution_filter}[ext=mp4]+bestaudio[ext=m4a]/best{resolution_filter}[ext=mp4]/best"
            video_command = base_command + ["-f", video_format_string, "--merge-output-format", "mp4"]
            video_info = _execute_yt_dlp_command(video_command)

        else: # 音訊下載邏輯（具備備援機制）
            final_suffix = f".{audio_format}"
            tag = f"[{audio_format}]"

            # 方案 A: 嘗試直接下載最佳音訊
            primary_audio_command = base_command + ["-x", "--audio-format", audio_format, "-f", "bestaudio/best"]
            try:
                log.info("音訊下載：執行主要方案 (直接下載音訊)...")
                video_info = _execute_yt_dlp_command(primary_audio_command)
                log.info("主要方案成功。")
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.strip().lower()
                # 檢查是否為平台限制錯誤
                if any(keyword in error_output for keyword in ["authentication", "login required", "sign in", "403 forbidden"]):
                    log.warning("主要方案失敗，偵測到平台限制。啟動備援方案...")

                    # 方案 B: 下載低畫質影片並從中提取音訊
                    # 使用 144p 作為一個穩定、低流量的影片來源
                    fallback_format = "bestvideo[height<=144][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]"
                    fallback_audio_command = base_command + ["-x", "--audio-format", audio_format, "-f", fallback_format, "--merge-output-format", "mp4"]
                    video_info = _execute_yt_dlp_command(fallback_audio_command)
                    log.info("備援方案成功。")
                else:
                    # 如果是其他類型的錯誤，則直接拋出，由外層處理
                    raise e

        # --- 統一下載成功後的處理流程 ---
        if not video_info:
            raise RuntimeError("下載完成，但未能獲取媒體資訊。")

        original_filepath_str = video_info.get('_filename')
        if not original_filepath_str:
            raise RuntimeError("yt-dlp 未在其 JSON 輸出中提供檔名。")

        original_path = Path(original_filepath_str)
        sanitized_stem = sanitize_filename(original_path.stem)
        new_filename = f"{tag}{sanitized_stem}{final_suffix}"
        final_path = original_path.with_name(new_filename)

        if original_path.exists():
            original_path.rename(final_path)
            log.info(f"檔案已成功重新命名為: {final_path}")
        else:
            log.warning(f"找不到原始下載檔案 {original_path}，無法重新命名。")
            if not final_path.exists():
                raise FileNotFoundError(f"找不到原始檔案或已重新命名的檔案。")

        final_result = {
            "type": "result", "status": "已完成",
            "output_path": str(final_path),
            "video_title": video_info.get("title", "Unknown Title"),
            "duration_seconds": video_info.get("duration", 0)
        }
        print(json.dumps(final_result), flush=True)
        log.info(f"✅ 媒體下載成功: {final_path}")

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