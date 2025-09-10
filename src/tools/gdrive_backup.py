import logging
import shutil
from pathlib import Path
import datetime

log = logging.getLogger(__name__)

# --- 核心備份函式 ---

def create_backup_archive() -> Path | None:
    """
    將資料庫檔案和 downloads 資料夾壓縮成一個 zip 檔案。

    :return: 成功時回傳壓縮檔的路徑 (Path 物件)，失敗時回傳 None。
    """
    log.info("開始建立備份壓縮檔...")
    try:
        # 定義要備份的來源路徑
        root_dir = Path(__file__).resolve().parent.parent.parent
        db_path = root_dir / "src" / "db" / "tasks.db"
        downloads_path = root_dir / "downloads"

        # 定義備份檔的儲存位置和檔名
        backup_dir = root_dir / "backups"
        backup_dir.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"backup_{timestamp}"
        archive_path = backup_dir / archive_name

        # 建立一個暫存目錄來組織備份內容
        temp_backup_src = backup_dir / f"temp_{timestamp}"
        temp_backup_src.mkdir()

        # 複製檔案到暫存目錄
        if db_path.exists():
            shutil.copy(db_path, temp_backup_src / "tasks.db")
            log.info(f"已將資料庫檔案複製到備份暫存區。")
        else:
            log.warning("找不到資料庫檔案 (tasks.db)，將不包含在備份中。")

        if downloads_path.exists() and any(downloads_path.iterdir()):
            # 為了避免在壓縮檔中包含 'downloads' 這個頂層目錄，
            # 我們將其內容複製到暫存目錄的 'downloads' 子目錄下
            temp_downloads_dest = temp_backup_src / "downloads"
            shutil.copytree(downloads_path, temp_downloads_dest)
            log.info(f"已將 downloads 資料夾複製到備份暫存區。")
        else:
            log.warning("找不到 downloads 資料夾或其為空，將不包含在備份中。")

        # 將暫存目錄壓縮
        shutil.make_archive(str(archive_path), 'zip', str(temp_backup_src))

        # 清理暫存目錄
        shutil.rmtree(temp_backup_src)

        final_archive_path = archive_path.with_suffix('.zip')
        log.info(f"✅ 備份壓縮檔成功建立於: {final_archive_path}")
        return final_archive_path

    except Exception as e:
        log.error(f"❌ 建立備份壓縮檔時發生錯誤: {e}", exc_info=True)
        # 清理可能存在的失敗產物
        if 'temp_backup_src' in locals() and temp_backup_src.exists():
            shutil.rmtree(temp_backup_src)
        return None

def upload_to_google_drive(file_path: Path) -> str | None:
    """
    將指定的檔案上傳到 Google Drive。

    注意：這是一個預留函式。完整的實作需要處理 OAuth 2.0 認證流程，
    這通常需要使用者透過瀏覽器進行一次性的授權，並需要一個 client_secrets.json 檔案。

    :param file_path: 要上傳的檔案路徑。
    :return: 成功時回傳檔案的線上連結，失敗時回傳 None。
    """
    log.warning("=== Google Drive 上傳功能說明 ===")
    log.warning("此功能需要 OAuth 2.0 客戶端憑證 (client_secrets.json)。")
    log.warning("執行時，可能需要您透過瀏覽器登入 Google 帳號並授權。")
    log.warning("由於此為後端背景任務，直接的瀏覽器互動不可行。")
    log.warning("一個常見的解決方案是：")
    log.warning("1. 執行一個一次性的本地腳本來完成授權，並儲存 token.json。")
    log.warning("2. 在此函式中讀取已儲存的 token.json 來建立服務。")
    log.warning("===================================")

    log.info(f"模擬上傳檔案: {file_path.name}...")
    # 在此處加入實際的 Google Drive API 上傳邏輯
    # from google.oauth2.credentials import Credentials
    # from googleapiclient.discovery import build
    # from googleapiclient.http import MediaFileUpload

    # 模擬成功，回傳一個假的連結
    mock_file_id = "1a2b3c4d5e6f7g8h9i0j"
    mock_url = f"https://drive.google.com/file/d/{mock_file_id}"
    log.info("模擬上傳成功！")
    return mock_url
