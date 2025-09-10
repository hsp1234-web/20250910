import json
import time
import argparse
import sys
from pathlib import Path
import shutil
import uuid

def main():
    """
    一個模擬的 YouTube 下載器。
    它會模仿真實工具的行為，印出進度 JSON 並在最後產出一個假的音訊檔案。
    """
    parser = argparse.ArgumentParser(description="模擬 YouTube 音訊下載。")
    parser.add_argument("--url", required=True, help="要處理的 YouTube URL。")
    parser.add_argument("--output-dir", required=True, help="儲存輸出檔案的目錄。")
    parser.add_argument("--download-type", help="下載類型 (audio/video)，此模擬器中未使用但為相容性保留。")
    args = parser.parse_args()

    try:
        # 模擬下載進度 (JULES'S FIX: Print all to stdout)
        print(json.dumps({"type": "progress", "percent": 10, "description": "正在連接模擬伺服器..."}), flush=True, file=sys.stderr)
        time.sleep(0.3)
        print(json.dumps({"type": "progress", "percent": 50, "description": "正在下載模擬音訊流..."}), flush=True, file=sys.stderr)
        time.sleep(0.5)
        print(json.dumps({"type": "progress", "percent": 100, "description": "正在完成模擬音訊檔案..."}), flush=True, file=sys.stderr)
        time.sleep(0.3)

        # 建立一個假的輸出檔案，透過複製測試治具 (fixture)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(exist_ok=True)

        # 定義測試治具的路徑 (相對於此腳本)
        script_dir = Path(__file__).resolve().parent
        fixture_path = script_dir.parent / "tests" / "fixtures" / "test_audio.mp3"

        # 為複製的檔案產生一個唯一的名稱，以避免測試間的衝突
        target_filename = f"e2e_test_{uuid.uuid4().hex[:8]}.mp3"
        target_path = output_dir / target_filename

        if not fixture_path.exists():
            # 如果治具檔案不存在，建立一個備用檔案並印出錯誤
            fallback_content = "FALLBACK - Fixture test_audio.mp3 not found."
            target_path.write_text(fallback_content, encoding='utf-8')
            error_result = {
                "type": "result",
                "status": "failed",
                "error": f"測試治具檔案遺失: {fixture_path}"
            }
            print(json.dumps(error_result), flush=True)
            sys.exit(1)

        # 複製治具檔案到目標路徑
        shutil.copy(fixture_path, target_path)

        # 產出最終的成功結果 JSON
        result = {
            "type": "result",
            "status": "已完成",
            "output_path": str(target_path),
            "video_title": f"'{args.url}' 的模擬影片標題",
            "duration_sec": 123,
            "mime_type": "audio/mp3"
        }
        print(json.dumps(result), flush=True)
        sys.exit(0)

    except Exception as e:
        # 產出錯誤結果 JSON
        error_result = {
            "type": "result",
            "status": "failed",
            "error": f"模擬下載器發生錯誤: {e}"
        }
        print(json.dumps(error_result), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
