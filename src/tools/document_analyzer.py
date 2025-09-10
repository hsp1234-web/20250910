import logging
import json
from pathlib import Path
import google.generativeai as genai
from PIL import Image

# --- 日誌和路徑設定 ---
log = logging.getLogger(__name__)
PROMPTS_FILE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "default_prompts.json"

# --- 提示詞載入 ---
def load_prompts() -> dict:
    try:
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log.critical(f"無法載入提示詞檔案: {e}", exc_info=True)
        return {}

ALL_PROMPTS = load_prompts()

# --- Gemini 分析核心函式 ---
def analyze_document_text(text: str, api_key: str) -> dict:
    """使用 Gemini 分析提供的文字，回傳摘要和關鍵字。"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro')
        prompt = ALL_PROMPTS['summarize_document_text'].format(document_text=text)
        response = model.generate_content(prompt)
        # 簡易解析，未來可做得更穩健
        # 假設格式是： "摘要：...\n關鍵字：..., ..., ..."
        parts = response.text.split("關鍵字：")
        summary = parts[0].replace("摘要：", "").strip()
        keywords = [k.strip() for k in parts[1].split(',')] if len(parts) > 1 else []
        return {"summary": summary, "keywords": keywords}
    except Exception as e:
        log.error(f"分析文件文字時發生錯誤: {e}", exc_info=True)
        return {"summary": f"分析失敗: {e}", "keywords": []}

def describe_image(image_path: Path, api_key: str) -> dict:
    """使用 Gemini Vision 模型描述單張圖片。"""
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-pro-vision')
        prompt = ALL_PROMPTS['describe_image']
        image = Image.open(image_path)
        response = model.generate_content([prompt, image])
        return {"description": response.text.strip()}
    except Exception as e:
        log.error(f"描述圖片 {image_path.name} 時發生錯誤: {e}", exc_info=True)
        return {"description": f"分析失敗: {e}"}

def analyze_document(text_content: str, image_paths: list[str], api_key: str) -> dict:
    """
    分析一份文件的完整內容（文字和圖片）。

    :param text_content: 從文件中提取的文字。
    :param image_paths: 從文件中提取的圖片路徑列表。
    :return: 一個包含所有分析結果的字典。
    """
    log.info("開始完整文件分析...")

    # 分析文字
    text_analysis = analyze_document_text(text_content, api_key)

    # 分析圖片 (可以考慮並行處理以加速)
    image_analyses = []
    for img_path_str in image_paths:
        img_path = Path(img_path_str)
        if img_path.exists():
            desc = describe_image(img_path, api_key)
            image_analyses.append({img_path_str: desc})

    log.info("文件分析完成。")
    return {
        "text_analysis": text_analysis,
        "image_analyses": image_analyses
    }
