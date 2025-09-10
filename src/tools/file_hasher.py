import hashlib
import logging
from pathlib import Path

log = logging.getLogger(__name__)

def calculate_sha256(file_path: Path) -> str | None:
    """
    計算給定檔案的 SHA256 雜湊值。

    :param file_path: 要計算雜湊值的檔案路徑 (Path 物件)。
    :return: 回傳十六進位格式的 SHA256 字串，如果檔案不存在或發生錯誤則回傳 None。
    """
    if not file_path.is_file():
        log.error(f"計算雜湊值失敗：檔案不存在於 {file_path}")
        return None

    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # 為了處理大檔案，一次讀取一個區塊
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        hex_digest = sha256_hash.hexdigest()
        log.info(f"檔案 {file_path.name} 的 SHA256 雜湊值為: {hex_digest}")
        return hex_digest
    except Exception as e:
        log.error(f"計算檔案 {file_path} 的雜湊值時發生錯誤: {e}", exc_info=True)
        return None
