# -*- coding: utf-8 -*-
# tools/transcriber.py

# --- JULES: 依賴懶加載機制 ---
# 在真正執行轉錄功能之前，先確保所有必要的依賴都已安裝。
import sys
from pathlib import Path

# 將專案根目錄加入到 sys.path，以便找到 scripts 模組
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))
try:
    from scripts.check_deps import ensure_dependencies
    # 定義此工具所需的依賴文件
    TRANSCRIBER_REQS = [str(ROOT_DIR / "requirements" / "transcriber.txt")]
    ensure_dependencies(TRANSCRIBER_REQS)
except ImportError as e:
    # 如果連 check_deps 都找不到，表示環境有嚴重問題
    print(f"致命錯誤：無法導入依賴檢查模組。請確認專案結構是否完整。 {e}", file=sys.stderr)
    sys.exit(1)
# --- 懶加載結束 ---

import time
import logging
import argparse
import torch
from pathlib import Path
from opencc import OpenCC
import json
import sys
from faster_whisper.utils import get_assets_path

# --- 全域常數 ---
# 定義下載進度回報的最小時間間隔 (秒)
PROGRESS_REPORT_INTERVAL = 0.5
# 繁簡轉換器
CC = OpenCC('s2t')

# --- 日誌設定 ---
# 將所有日誌和進度訊息導向標準錯誤流
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger('transcriber_tool')

class Transcriber:
    def __init__(self, model_size="large-v3"):
        self.model_size = model_size
        self.model = self._load_model()
        self.last_report_time = 0

    def _load_model(self):
        """載入 faster-whisper 模型。"""
        log.info(f"準備載入 '{self.model_size}' 模型...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        log.info(f"裝置: {device}, 計算類型: {compute_type}")

        start_time = time.time()
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(self.model_size, device=device, compute_type=compute_type)
            duration = time.time() - start_time
            log.info(f"✅ 成功載入 '{self.model_size}' 模型到 {device.upper()}！耗時: {duration:.2f} 秒。")
            return model
        except ImportError as e:
            log.critical(f"❌ 模型載入失敗：缺少 'faster_whisper' 或 'torch' 模組。請確認環境已正確安裝。")
            raise e
        except Exception as e:
            log.critical(f"❌ 載入 '{self.model_size}' 模型時發生未預期錯誤: {e}", exc_info=True)
            raise e

    def _report_progress(self, progress: float):
        """以 JSON 格式回報進度到 stdout，並控制回報頻率。"""
        current_time = time.time()
        if current_time - self.last_report_time >= PROGRESS_REPORT_INTERVAL:
            progress_data = {
                "type": "progress",
                "percent": round(progress, 2),
                "description": "AI 正在處理音訊..."
            }
            # 使用 print 將 JSON 輸出到 stdout，並確保立即刷新
            print(json.dumps(progress_data), flush=True)
            self.last_report_time = current_time

    def transcribe(self, audio_path: str, language: str = None, beam_size: int = 5) -> str:
        """執行音訊轉錄。"""
        try:
            log.info("模型載入完成，開始轉錄...")

            segments, info = self.model.transcribe(audio_path, beam_size=beam_size, language=language, word_timestamps=True)

            detected_lang_msg = f"'{info.language}' (機率: {info.language_probability:.2f})"
            if language:
                log.info(f"🌍 使用者指定語言: '{language}'，模型偵測到 {detected_lang_msg}")
            else:
                log.info(f"🌍 未指定語言，模型自動偵測到 {detected_lang_msg}")

            full_transcript = []
            total_duration = info.duration

            for segment in segments:
                # 簡轉繁
                text_simplified = segment.text
                text_traditional = CC.convert(text_simplified)

                # 建立包含時間戳的單行文字
                start_time = time.strftime('%H:%M:%S', time.gmtime(segment.start))
                end_time = time.strftime('%H:%M:%S', time.gmtime(segment.end))
                line = f"[{start_time} --> {end_time}] {text_traditional}"
                full_transcript.append(line)

                # 回報進度
                progress = (segment.end / total_duration) * 100
                self._report_progress(progress)

                # 也將每個片段的詳細資訊以 JSON 格式輸出到 stdout
                segment_data = {
                    "type": "segment",
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": text_traditional
                }
                print(json.dumps(segment_data), flush=True)

            log.info("✅ 轉錄完成。")
            return "\n".join(full_transcript)

        except Exception as e:
            log.critical(f"❌ 轉錄過程中發生錯誤: {e}", exc_info=True)
            raise e

def check_model_exists(model_size: str) -> bool:
    """檢查模型是否已在本地快取。"""
    try:
        # faster-whisper 將模型存在 huggingface 快取目錄
        # 我們透過檢查模型目錄是否存在來判斷
        assets_dir = get_assets_path()
        model_path = Path(assets_dir) / f"models--Systran--faster-whisper-{model_size}"
        return model_path.exists()
    except Exception as e:
        log.error(f"檢查模型 '{model_size}' 時發生錯誤: {e}")
        return False

def download_model_with_progress(model_size: str):
    """下載模型並在 stdout 上顯示進度。"""
    log.info(f"📥 開始下載 '{model_size}' 模型...")
    try:
        from faster_whisper import WhisperModel
        # 載入模型時，如果模型不存在，它會自動下載
        # 我們可以利用這個行為，但 faster-whisper 本身不提供下載進度回呼
        # 這是一個簡化的實現，只在開始和結束時提供回饋
        print(json.dumps({"type": "progress", "percent": 0, "description": f"開始下載 {model_size} 模型..."}), flush=True)
        WhisperModel(model_size, download_root=None) # download_root=None 使用預設快取路徑
        print(json.dumps({"type": "progress", "percent": 100, "description": "模型下載完成。"}), flush=True)
        log.info(f"✅ 模型 '{model_size}' 下載或驗證成功。")
    except Exception as e:
        log.critical(f"❌ 下載模型 '{model_size}' 時失敗: {e}", exc_info=True)
        # 將錯誤訊息也以 JSON 格式輸出，以便上層捕捉
        print(json.dumps({"type": "error", "message": str(e)}), flush=True)
        raise

def main():
    """主函式，解析命令列參數並執行相應操作。"""
    parser = argparse.ArgumentParser(description="一個多功能轉錄與模型管理工具。")
    # 主指令
    parser.add_argument("--command", type=str, default="transcribe", choices=["transcribe", "check", "download"], help="要執行的操作。")
    # 轉錄參數
    parser.add_argument("--audio_file", type=str, help="[transcribe] 需要轉錄的音訊檔案路徑。")
    parser.add_argument("--output_file", type=str, help="[transcribe] 儲存轉錄結果的檔案路徑。")
    parser.add_argument("--language", type=str, default=None, help="[transcribe] 音訊的語言。")
    parser.add_argument("--beam_size", type=int, default=5, help="[transcribe] 解碼時使用的光束大小。")
    # 通用參數
    parser.add_argument("--model_size", type=str, default="tiny", help="要使用/檢查/下載的模型大小。")

    args = parser.parse_args()

    if args.command == "check":
        if check_model_exists(args.model_size):
            print("exists", flush=True) # 輸出到 stdout
        else:
            print("not_exists", flush=True) # 輸出到 stdout

    elif args.command == "download":
        download_model_with_progress(args.model_size)

    elif args.command == "transcribe":
        if not args.audio_file or not args.output_file:
            log.critical("錯誤：執行 'transcribe' 指令時，必須提供 --audio_file 和 --output_file。")
            exit(1)
        try:
            transcriber = Transcriber(model_size=args.model_size)
            result_text = transcriber.transcribe(args.audio_file, args.language, args.beam_size)
            output_path = Path(args.output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(result_text)
            log.info(f"✅ 轉錄結果已成功寫入: {output_path}")
        except Exception as e:
            log.critical(f"❌ 在執行過程中發生致命錯誤: {e}", exc_info=True)
            # 可以在此處建立一個錯誤標記檔案，以便外部執行器知道發生了問題
            error_file = Path(args.output_file).parent / f"{Path(args.output_file).stem}.error"
            error_file.write_text(str(e), encoding='utf-8')
            exit(1) # 以非零狀態碼退出，表示失敗

if __name__ == "__main__":
    main()
