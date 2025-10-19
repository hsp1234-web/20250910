# src/tools/youtube_downloader.py
import argparse
import logging
import sys
import subprocess
from pathlib import Path

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)] # 改為 stdout
)
log = logging.getLogger('youtube_downloader_worker')

# --- 常數設定 ---
# 下載超時設定為 30 分鐘
DOWNLOAD_TIMEOUT_SECONDS = 1800

def download_audio_worker(youtube_url: str, output_dir: Path, task_hash: str):
    """
    一個單一職責的背景工作函式，專門負責下載音訊。
    它會嘗試下載最高品質的原生 M4A 音訊，以下載速度最快。
    檔案將被直接下載到指定的目錄中，並以任務雜湊命名。
    """
    log.info(f"背景下載工人已啟動。URL: {youtube_url}, 目標目錄: {output_dir}, 任務雜湊: {task_hash}")

    # 確保輸出目錄存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 輸出範本，使用傳入的 task_hash 作為檔名（不含副檔名）
    output_template = str(output_dir / task_hash) + ".%(ext)s"

    command = [
        sys.executable, "-m", "yt_dlp",
        # --- 指令優化 ---
        # 1. -f bestaudio[ext=m4a]/bestaudio:
        #    優先選擇原生就是 m4a 的最佳音訊，如果沒有，再選擇其他格式的最佳音訊。
        #    這能最大程度地避免下載後再轉換格式，提升速度並減少錯誤。
        "-f", "bestaudio[ext=m4a]/bestaudio",
        # 2. -x, --audio-format m4a:
        #    如果找不到原生的 m4a，這個指令會確保將下載的音訊轉換為 m4a。
        #    這是確保最終檔案格式一致性的備用方案。
        "-x", "--audio-format", "m4a",
        # --- 其他穩定性選項 ---
        "--quiet",                     # 只輸出關鍵資訊
        "--no-part",                   # 不使用 .part 暫存檔，直接寫入最終檔案
        "--fragment-retries", "infinite", # 無限次重試片段
        # --- 輸出路徑 ---
        "-o", output_template,
        youtube_url
    ]

    log.info(f"執行 yt-dlp 指令: {' '.join(command)}")

    try:
        # 執行指令並設定超時
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            encoding='utf-8',
            timeout=DOWNLOAD_TIMEOUT_SECONDS
        )
        log.info(f"✅ 下載成功。URL: {youtube_url}。標準輸出:\n{result.stdout}")

    except subprocess.TimeoutExpired:
        log.error(f"❌ 下載超時 ({DOWNLOAD_TIMEOUT_SECONDS}秒)。URL: {youtube_url}")
        # 超時也需要退出，並返回非零碼表示錯誤
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        # check=True 會在返回碼非0時拋出此例外
        log.error(f"❌ yt-dlp 執行失敗。URL: {youtube_url}。返回碼: {e.returncode}\nStderr: {e.stderr}")
        sys.exit(1)
    except Exception as e:
        log.error(f"❌ 下載過程中發生未預期的錯誤。URL: {youtube_url}。錯誤: {e}", exc_info=True)
        sys.exit(1)

def main():
    """
    腳本主進入點，用於從命令列執行下載工人。
    """
    parser = argparse.ArgumentParser(description="單一職責的媒體下載工人。")
    parser.add_argument("--url", type=str, required=True, help="要下載的 YouTube 影片網址。")
    parser.add_argument("--output-dir", type=str, required=True, help="儲存下載檔案的目錄。")
    parser.add_argument("--task-hash", type=str, required=True, help="用於命名檔案的唯一任務雜湊值。")
    args = parser.parse_args()

    output_path = Path(args.output_dir)

    download_audio_worker(args.url, output_path, args.task_hash)

if __name__ == "__main__":
    main()