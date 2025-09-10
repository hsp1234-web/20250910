import os
import logging
from typing import Dict, Any

try:
    import fitz # PyMuPDF
except ImportError:
    logging.warning("PyMuPDF (fitz) not found. PDF parsing will be disabled.")
    fitz = None

def parse_pdf(pdf_path: str, image_output_dir: str) -> Dict[str, Any]:
    """
    解析指定的 PDF 檔案，提取文字和圖片。
    - pdf_path: PDF 檔案的路徑。
    - image_output_dir: 儲存提取圖片的目錄。
    """
    if not fitz:
        logging.error("無法解析 PDF，因為 PyMuPDF (fitz) 模組未安裝。")
        return None
    if not os.path.exists(pdf_path):
        logging.error(f"找不到指定的 PDF 檔案：{pdf_path}")
        return None
    os.makedirs(image_output_dir, exist_ok=True)
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logging.error(f"使用 PyMuPDF 開啟檔案 '{pdf_path}' 失敗: {e}")
        return None
    all_text, extracted_image_paths = [], []
    try:
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            all_text.append(page.get_text())
            for img_index, img in enumerate(page.get_images(full=True)):
                xref = img[0]
                base_image = doc.extract_image(xref)
                image_bytes, image_ext = base_image["image"], base_image["ext"]
                pdf_filename = os.path.splitext(os.path.basename(pdf_path))[0]
                image_filename = f"{pdf_filename}_page{page_num+1}_img{img_index}.{image_ext}"
                image_path = os.path.join(image_output_dir, image_filename)
                with open(image_path, "wb") as image_file:
                    image_file.write(image_bytes)
                extracted_image_paths.append(image_path)
        logging.info(f"✅ 成功解析 '{pdf_path}'. 找到 {doc.page_count} 頁, {len(extracted_image_paths)} 張圖片。")
        return {"text": "\\n".join(all_text), "image_paths": extracted_image_paths, "page_count": doc.page_count}
    except Exception as e:
        logging.error(f"處理 PDF '{pdf_path}' 過程中發生錯誤: {e}")
        return None
    finally:
        doc.close()
