import logging
from pathlib import Path
from PIL import Image

log = logging.getLogger(__name__)

import io
import shutil

def compress_image(image_path_str: str, output_dir_str: str, target_width: int = 800, quality: int = 85) -> str | None:
    """
    智慧地壓縮指定的圖片。
    - 如果圖片寬度大於目標寬度，則進行縮放。
    - 將圖片儲存為 JPEG 格式。
    - 如果處理後的檔案大小沒有變小，則直接複製原始檔案到目標路徑。

    :param image_path_str: 來源圖片的路徑字串。
    :param output_dir_str: 儲存壓縮圖片的目錄路徑字串。
    :param target_width: 壓縮後的目標寬度（像素）。
    :param quality: 壓縮品質 (1-95)，僅對 JPEG 有效。
    :return: 處理後圖片的路徑字串，或在失敗時回傳 None。
    """
    try:
        image_path = Path(image_path_str)
        output_dir = Path(output_dir_str)

        if not image_path.is_file():
            log.error(f"圖片壓縮失敗：找不到來源檔案 {image_path}")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        original_size = image_path.stat().st_size
        img = Image.open(image_path)

        # --- 智慧縮放 ---
        # 只有當圖片寬度大於目標寬度時才進行縮放
        if img.width > target_width:
            aspect_ratio = img.height / img.width
            new_height = int(target_width * aspect_ratio)
            img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

        # 轉換為 RGB 以避免儲存為 JPEG 時的透明度問題
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # --- 嘗試在記憶體中壓縮 ---
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG', quality=quality, optimize=True)
        compressed_size = buffer.tell()

        # --- 智慧儲存 ---
        # 統一輸出檔名格式
        output_filename = output_dir / f"{image_path.stem}_compressed.jpg"

        # 只有當壓縮後的檔案比原始檔案小時，才儲存壓縮版本
        if compressed_size < original_size:
            with open(output_filename, 'wb') as f:
                f.write(buffer.getvalue())
            log.info(f"成功將圖片 {image_path.name} 壓縮並儲存至 {output_filename} (大小從 {original_size} -> {compressed_size} 位元組)")
        else:
            # 否則，直接將原始檔案複製到目標路徑
            shutil.copy(image_path, output_filename)
            log.warning(f"圖片 {image_path.name} 壓縮後大小未減小 ({original_size} -> {compressed_size} 位元組)，已直接複製原始檔案至 {output_filename}。")

        return str(output_filename)

    except Exception as e:
        log.error(f"壓縮圖片 {image_path_str} 時發生未預期的錯誤: {e}", exc_info=True)
        return None
