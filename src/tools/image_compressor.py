import logging
from pathlib import Path
from PIL import Image

log = logging.getLogger(__name__)

def compress_image(image_path_str: str, output_dir_str: str, target_width: int = 800, quality: int = 85) -> str | None:
    """
    壓縮指定的圖片。

    :param image_path_str: 來源圖片的路徑字串。
    :param output_dir_str: 儲存壓縮圖片的目錄路徑字串。
    :param target_width: 壓縮後的目標寬度（像素）。
    :param quality: 壓縮品質 (1-95)，僅對 JPEG 有效。
    :return: 壓縮後圖片的路徑字串，或在失敗時回傳 None。
    """
    try:
        image_path = Path(image_path_str)
        output_dir = Path(output_dir_str)

        if not image_path.is_file():
            log.error(f"圖片壓縮失敗：找不到來源檔案 {image_path}")
            return None

        # 確保輸出目錄存在
        output_dir.mkdir(parents=True, exist_ok=True)

        img = Image.open(image_path)

        # 轉換為 RGB 以避免儲存為 JPEG 時的透明度問題
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 計算新的高度以保持長寬比
        aspect_ratio = img.height / img.width
        new_height = int(target_width * aspect_ratio)

        # 縮放圖片
        resized_img = img.resize((target_width, new_height), Image.Resampling.LANCZOS)

        # 建立新的檔名並儲存
        output_filename = output_dir / f"{image_path.stem}_compressed.jpg"
        resized_img.save(output_filename, "jpeg", quality=quality, optimize=True)

        log.info(f"成功將圖片 {image_path.name} 壓縮並儲存至 {output_filename}")
        return str(output_filename)

    except Exception as e:
        log.error(f"壓縮圖片 {image_path_str} 時發生未預期的錯誤: {e}", exc_info=True)
        return None
