# -*- coding: utf-8 -*-
# tools/mock_transcriber.py
import time
import logging
import argparse
from pathlib import Path
import json
import sys

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger('mock_transcriber_tool')

def mock_transcribe(audio_file: str, output_file: str):
    """
    模擬一個長時間運行的轉錄過程，並在 stdout 上輸出模擬的 JSON 進度。
    """
    log.info(f"🎤 (模擬) 開始處理轉錄任務: {audio_file}")
    total_duration = 15.0  # 假設音訊長度為 15 秒
    mock_segments = [
        {"start": 0.0, "end": 5.0, "text": "你好，這是一個模擬的語音轉錄。"},
        {"start": 5.5, "end": 10.0, "text": "這個工具會模擬真實轉錄器的輸出。"},
        {"start": 10.5, "end": 14.8, "text": "現在，模擬即將結束。"}
    ]

    full_transcript = []
    for i, segment in enumerate(mock_segments):
        time.sleep(0.5) # 模擬處理延遲
        progress = (segment['end'] / total_duration) * 100
        # 模擬進度回報
        print(json.dumps({"type": "progress", "percent": round(progress, 2), "description": "AI 模擬處理中..."}), flush=True, file=sys.stdout)
        # 模擬片段回報
        print(json.dumps(segment), flush=True, file=sys.stdout)
        full_transcript.append(segment['text'])

    # 寫入最終的完整檔案
    Path(output_file).write_text("\n".join(full_transcript), encoding='utf-8')
    log.info(f"✅ (模擬) 轉錄結果已寫入: {output_file}")


def main():
    """主函式，解析命令列參數並執行相應操作。"""
    parser = argparse.ArgumentParser(description="一個與真實轉錄器介面相容的模擬工具。")
    parser.add_argument("--command", type=str, default="transcribe", choices=["transcribe", "check", "download"], help="要執行的操作。")
    # 轉錄參數
    parser.add_argument("--audio_file", type=str, help="[transcribe] 需要轉錄的音訊檔案路徑。")
    parser.add_argument("--output_file", type=str, help="[transcribe] 儲存轉錄結果的檔案路徑。")
    parser.add_argument("--language", type=str, default=None, help="[transcribe] 音訊的語言 (被忽略)。")
    parser.add_argument("--beam_size", type=int, default=5, help="[transcribe] 解碼時使用的光束大小 (被忽略)。")
    # 通用參數
    parser.add_argument("--model_size", type=str, default="tiny", help="要使用/檢查/下載的模型大小 (被忽略)。")

    args = parser.parse_args()

    if args.command == "check":
        # 模擬模型永遠存在
        log.info(f"(模擬) 檢查模型 '{args.model_size}'，回報: 永遠存在。")
        print("exists", flush=True)

    elif args.command == "download":
        log.info(f"📥 (模擬) 開始下載 '{args.model_size}' 模型...")
        time.sleep(1) # 模擬下載延遲
        print(json.dumps({"type": "progress", "percent": 100, "description": "模型下載完成。"}), flush=True)
        log.info(f"✅ (模擬) 模型 '{args.model_size}' 下載完成。")

    elif args.command == "transcribe":
        if not args.audio_file or not args.output_file:
            log.critical("錯誤：執行 'transcribe' 指令時，必須提供 --audio_file 和 --output_file。")
            exit(1)
        try:
            mock_transcribe(args.audio_file, args.output_file)
        except Exception as e:
            log.critical(f"❌ (模擬) 在執行過程中發生致命錯誤: {e}", exc_info=True)
            error_file = Path(args.output_file).parent / f"{Path(args.output_file).stem}.error"
            error_file.write_text(str(e), encoding='utf-8')
            exit(1)

if __name__ == "__main__":
    main()
