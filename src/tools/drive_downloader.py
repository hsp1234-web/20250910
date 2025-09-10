import os
import logging
import subprocess
import re

def download_file(url: str, output_dir: str, file_name: str = None):
    """
    從指定的 URL (特別是 Google Drive) 下載檔案。
    此函式為一個生成器，會即時回傳下載進度。

    Args:
        url (str): 檔案的 Google Drive 分享連結。
        output_dir (str): 儲存檔案的目錄。
        file_name (str): 儲存的檔案名稱（不含副檔名）。

    Yields:
        dict: 一個包含進度更新或最終結果的字典。
              - {'type': 'progress', 'value': int}  (進度百分比)
              - {'type': 'completed', 'path': str} (完成後的檔案路徑)
              - {'type': 'error', 'message': str} (發生錯誤)
    """
    os.makedirs(output_dir, exist_ok=True)
    # 我們提供一個基礎路徑給 gdown，它可能會透過 --fuzzy 參數自動加上副檔名
    output_base_path = os.path.join(output_dir, file_name) if file_name else os.path.join(output_dir, "download")
    logging.info(f"準備從 URL 下載：{url} 至基礎路徑 {output_base_path}")

    # 為 subprocess 建構指令
    # 使用 -O 指定輸出檔案路徑。--fuzzy 允許 gdown 猜測並修正下載連結。
    command = ['gdown', url, '-O', output_base_path, '--fuzzy']

    try:
        # 啟動子程序
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # 將 stderr 合併到 stdout
            text=True,
            encoding='utf-8',
            bufsize=1  # 行緩衝
        )

        last_yielded_percent = -1
        # 即時讀取輸出
        for line in iter(process.stdout.readline, ''):
            # 記錄原始輸出以供除錯
            logging.debug(f"gdown output: {line.strip()}")

            # 使用正規表示式尋找進度百分比
            match = re.search(r'(\d+)\s*%', line)
            if match:
                percent = int(match.group(1))
                # 只有在百分比增加時才回傳，避免訊息重複
                if percent > last_yielded_percent:
                    last_yielded_percent = percent
                    yield {'type': 'progress', 'value': percent}

        process.stdout.close()
        return_code = process.wait()

        if return_code == 0:
            logging.info(f"gdown 處理程序成功完成。正在確認最終檔案路徑...")
            # 尋找實際下載的檔案，因為 --fuzzy 可能會新增副檔名
            found_path = None
            base_filename = os.path.basename(output_base_path)
            for f in os.listdir(output_dir):
                if f.startswith(base_filename):
                    found_path = os.path.join(output_dir, f)
                    logging.info(f"✅ 檔案成功下載至：{found_path}")
                    yield {'type': 'completed', 'path': found_path}
                    break

            if not found_path:
                error_msg = "gdown 執行完畢但找不到對應的檔案。可能是下載了 0 位元組的檔案。"
                logging.error(f"❌ {error_msg}")
                yield {'type': 'error', 'message': error_msg}
        else:
            error_msg = f"gdown 處理程序以錯誤碼 {return_code} 結束。請檢查日誌以了解詳情。"
            logging.error(f"❌ {error_msg}")
            yield {'type': 'error', 'message': error_msg}

    except FileNotFoundError:
        error_msg = "gdown 指令未找到。請確認 gdown 套件已安裝並在系統 PATH 中。"
        logging.error(f"❌ {error_msg}")
        yield {'type': 'error', 'message': error_msg}
    except Exception as e:
        error_msg = f"下載過程中發生嚴重錯誤：{e}"
        logging.error(f"❌ {error_msg}", exc_info=True)
        yield {'type': 'error', 'message': error_msg}
