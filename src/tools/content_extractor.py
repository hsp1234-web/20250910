import logging
from pathlib import Path
import fitz  # PyMuPDF
import docx
from pptx import Presentation
import io
from PIL import Image
import easyocr

log = logging.getLogger(__name__)

# --- OCR 模組初始化 ---
# 將 OCR Reader 初始化為一個全域變數，避免重複載入模型
# 這是一個昂貴的操作，我們希望在應用程式生命週期中只做一次。
OCR_READER = None
try:
    # 指定辨識繁體中文和英文
    OCR_READER = easyocr.Reader(['ch_tra', 'en'])
    log.info("✅ EasyOCR Reader 成功初始化 (繁體中文 + 英文)。")
except Exception as e:
    log.warning(f"⚠️ 無法初始化 EasyOCR Reader，OCR 功能將被停用。錯誤: {e}")

def perform_ocr_on_image(image_path: str) -> str:
    """
    使用全域的 EasyOCR Reader 對單一圖片檔案執行光學字元辨識。

    :param image_path: 要辨識的圖片檔案路徑。
    :return: 辨識出的文字字串，如果失敗則為空字串。
    """
    if not OCR_READER:
        log.warning(f"由於 OCR Reader 未初始化，跳過對 '{image_path}' 的辨識。")
        return ""
    try:
        log.info(f"正在對圖片進行 OCR: {image_path}...")
        # detail=0 只回傳文字，paragraph=True 會嘗試將文字塊合併成段落
        result = OCR_READER.readtext(image_path, detail=0, paragraph=True)
        text = "\n".join(result)
        log.info(f"✅ 成功對 '{Path(image_path).name}' 進行 OCR，提取了 {len(text)} 個字元。")
        return text
    except Exception as e:
        log.error(f"❌ 對圖片 '{image_path}' 進行 OCR 時發生錯誤: {e}", exc_info=True)
        return ""

def extract_from_pdf(file_path: Path, output_dir: Path) -> dict:
    """從 PDF 檔案中提取所有文字和圖片。"""
    text_content = ""
    image_paths = []
    try:
        pdf_document = fitz.open(file_path)
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            text_content += page.get_text() + "\n"

            image_list = page.get_images(full=True)
            for img_index, img in enumerate(image_list):
                xref = img[0]
                base_image = pdf_document.extract_image(xref)
                image_bytes = base_image["image"]
                image_ext = base_image["ext"]

                image_filename = output_dir / f"{file_path.stem}_page{page_num+1}_img{img_index}.{image_ext}"
                with open(image_filename, "wb") as img_file:
                    img_file.write(image_bytes)
                image_paths.append(image_filename)
        log.info(f"從 PDF '{file_path.name}' 中成功提取 {len(image_paths)} 張圖片和 {len(text_content)} 字元。")
    except Exception as e:
        log.error(f"從 PDF '{file_path.name}' 提取內容時發生錯誤: {e}", exc_info=True)
    return {"text": text_content.strip(), "image_paths": image_paths}

def extract_from_docx(file_path: Path, output_dir: Path) -> dict:
    """從 DOCX 檔案中提取所有文字和圖片。"""
    text_content = ""
    image_paths = []
    try:
        doc = docx.Document(file_path)
        for para in doc.paragraphs:
            text_content += para.text + "\n"

        for i, rel in enumerate(doc.part.rels.values()):
            if "image" in rel.target_ref:
                image_data = rel.target_part.blob
                try:
                    image = Image.open(io.BytesIO(image_data))
                    ext = image.format.lower()
                except Exception:
                    ext = 'png'
                image_filename = output_dir / f"{file_path.stem}_img{i}.{ext}"
                with open(image_filename, "wb") as img_file:
                    img_file.write(image_data)
                image_paths.append(image_filename)
        log.info(f"從 DOCX '{file_path.name}' 中成功提取 {len(image_paths)} 張圖片和 {len(text_content)} 字元。")
    except Exception as e:
        log.error(f"從 DOCX '{file_path.name}' 提取內容時發生錯誤: {e}", exc_info=True)
    return {"text": text_content.strip(), "image_paths": image_paths}

def extract_from_pptx(file_path: Path, output_dir: Path) -> dict:
    """從 PPTX 檔案中提取所有文字和圖片。"""
    text_content = ""
    image_paths = []
    try:
        prs = Presentation(file_path)
        img_index = 0
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "image"):
                    image = shape.image
                    image_bytes = image.blob
                    ext = image.ext
                    image_filename = output_dir / f"{file_path.stem}_img{img_index}.{ext}"
                    with open(image_filename, "wb") as img_file:
                        img_file.write(image_bytes)
                    image_paths.append(image_filename)
                    img_index += 1
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            text_content += run.text + " "
                    text_content += "\n"
        log.info(f"從 PPTX '{file_path.name}' 中成功提取 {len(image_paths)} 張圖片和 {len(text_content)} 字元。")
    except Exception as e:
        log.error(f"從 PPTX '{file_path.name}' 提取內容時發生錯誤: {e}", exc_info=True)
    return {"text": text_content.strip(), "image_paths": image_paths}

def extract_content(file_path_str: str, image_output_dir_str: str) -> dict | None:
    """
    一個主函式，根據副檔名分派任務給對應的提取器。
    現在會同時提取文字與圖片，並對圖片執行 OCR。

    :param file_path_str: 來源檔案的完整路徑字串。
    :param image_output_dir_str: 儲存提取出的圖片的目錄路徑字串。
    :return: 一個包含 'text' 和 'image_paths' 的字典，或在失敗時回傳 None。
    """
    file_path = Path(file_path_str)
    output_dir = Path(image_output_dir_str)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not file_path.is_file():
        log.error(f"檔案不存在於: {file_path}")
        return None

    ext = file_path.suffix.lower()
    content_data = {"text": "", "image_paths": []}

    if ext == '.pdf':
        content_data = extract_from_pdf(file_path, output_dir)
    elif ext == '.docx':
        content_data = extract_from_docx(file_path, output_dir)
    elif ext == '.pptx':
        content_data = extract_from_pptx(file_path, output_dir)
    else:
        log.warning(f"不支援的檔案類型: {ext}。跳過內容提取。")
        return {"text": "", "image_paths": []}

    # --- 新增的 OCR 處理流程 ---
    if content_data.get("image_paths"):
        log.info(f"發現 {len(content_data['image_paths'])} 張圖片，開始執行 OCR...")
        ocr_texts = []
        for image_path in content_data["image_paths"]:
            ocr_text = perform_ocr_on_image(image_path)
            if ocr_text:
                # 為辨識出的文字加上清晰的標記
                ocr_texts.append(f"\n\n--- [圖片內容開始: {Path(image_path).name}] ---\n{ocr_text}\n--- [圖片內容結束] ---\n")

        if ocr_texts:
            # 將所有 OCR 文字附加到主文字內容的末尾
            full_ocr_text = "".join(ocr_texts)
            content_data["text"] += full_ocr_text
            log.info(f"已將 {len(ocr_texts)} 張圖片的 OCR 結果附加到主文字內容中。")

    if content_data and content_data.get("text"):
        original_text = content_data["text"]
        sanitized_text = original_text.encode('utf-8', 'replace').decode('utf-8')
        if original_text != sanitized_text:
            log.warning(f"檔案 '{file_path.name}' 的文字內容中偵測到並修正了無效字元。")
        content_data["text"] = sanitized_text

    content_data["image_paths"] = [str(p) for p in content_data["image_paths"]]
    return content_data
