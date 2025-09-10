# src/tools/mock_downloader_for_test.py
import argparse
import json
import sys
from pathlib import Path
import time

def main():
    """
    一個專門用於 E2E 測試的模擬下載器。
    它會建立一個具有指定名稱的假檔案，並回傳一個模擬 yt-dlp 的成功 JSON。
    """
    parser = argparse.ArgumentParser(description="模擬媒體下載工具。")
    parser.add_argument("--url", type=str, required=True)
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--download-type", type=str, default="audio")
    parser.add_argument("--custom-filename", type=str, default=None)
    parser.add_argument("--cookies-file", type=str, default=None)
    args = parser.parse_args()

    try:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 如果沒有提供自訂檔名，就從 URL 中產生一個
        video_title = args.custom_filename
        if not video_title:
            # 從 mock:// 後面的部分提取標題
            video_title = args.url.split("mock://")[1]

        # 根據下載類型決定副檔名
        extension = ".mp3" if args.download_type == "audio" else ".mp4"

        # 建立假檔案
        final_path = output_dir / f"{video_title}{extension}"
        final_path.touch() # 建立一個空檔案

        # 準備並印出模擬的成功 JSON 輸出
        final_result = {
            "type": "result",
            "status": "已完成",
            "output_path": str(final_path),
            "video_title": video_title,
            "duration_seconds": 123 # 模擬的時長
        }
        print(json.dumps(final_result), flush=True)
        sys.exit(0)

    except Exception as e:
        # 如果發生任何錯誤，印出錯誤的 JSON
        error_result = {"type": "result", "status": "failed", "error": str(e)}
        print(json.dumps(error_result), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
