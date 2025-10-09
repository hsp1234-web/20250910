import time
import base64
from pathlib import Path
import asyncio

# --- 設定 ---
IMAGE_PATH = Path('test_ocr_image.png')
TEXT_PROMPT = "請精確地、只提取這張圖片中的所有繁體中文和英數文字，不要包含任何描述、解釋或格式化。直接輸出文字即可。"

def print_header(title):
    """打印漂亮的標題頭。"""
    print("\n" + "="*60)
    print(f"🔬 {title}")
    print("="*60)

def print_result(model_name, duration, result_text):
    """格式化打印測試結果。"""
    print(f"\n--- {model_name} 測試結果 ---")
    print(f"⏱️ 執行時間: {duration:.4f} 秒")
    print("📜 辨識內容:")
    print("-" * 20)
    print(result_text.strip())
    print("-" * 20)

# --- 測試函式 ---

async def test_ocrflux():
    """測試 OCRFlux-3B 模型 (透過 Ollama)。"""
    model_name = 'myaniu/OCRFlux-3B:Q8_0'
    print_header(f"正在測試 Ollama 模型: {model_name}")

    try:
        import ollama
        client = ollama.Client()
        # 確認連線
        client.list()
        print("✅ 成功連接到 Ollama 服務。")

        if not IMAGE_PATH.exists():
            print(f"❌ 圖片檔案不存在: {IMAGE_PATH}")
            return

        with open(IMAGE_PATH, 'rb') as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

        start_time = time.time()

        response = await asyncio.to_thread(
            client.chat,
            model=model_name,
            messages=[
                {
                    'role': 'user',
                    'content': TEXT_PROMPT,
                    'images': [encoded_image]
                }
            ]
        )
        result_text = response['message']['content']
        end_time = time.time()

        print_result("OCRFlux-3B (Ollama)", end_time - start_time, result_text)

    except ImportError:
        print("⚠️ 跳過測試：`ollama` 套件未安裝。")
    except Exception as e:
        print(f"❌ 執行測試時發生錯誤: {e}")

async def test_easyocr():
    """測試 EasyOCR。"""
    print_header("正在測試 EasyOCR")
    try:
        import easyocr
        from PIL import Image

        if not IMAGE_PATH.exists():
            print(f"❌ 圖片檔案不存在: {IMAGE_PATH}")
            return

        start_time = time.time()

        # 初始化 Reader (包含模型下載和載入)
        # 我們將初始化時間也計入，以反映首次使用的完整體驗
        reader = easyocr.Reader(['ch_tra', 'en'], gpu=False)

        # 讀取文字
        result = reader.readtext(str(IMAGE_PATH), detail=0, paragraph=True)
        result_text = "\n".join(result)

        end_time = time.time()

        print_result("EasyOCR", end_time - start_time, result_text)

    except ImportError:
        print("⚠️ 跳過測試：`easyocr` 或 `Pillow` 套件未安裝。")
    except Exception as e:
        print(f"❌ 執行測試時發生錯誤: {e}")

async def test_tesseract():
    """測試 Tesseract OCR。"""
    print_header("正在測試 Tesseract")
    try:
        import pytesseract
        from PIL import Image

        if not IMAGE_PATH.exists():
            print(f"❌ 圖片檔案不存在: {IMAGE_PATH}")
            return

        start_time = time.time()

        # 直接使用 pytesseract 進行辨識
        img = Image.open(IMAGE_PATH)
        result_text = pytesseract.image_to_string(img, lang='chi_tra+eng')

        end_time = time.time()

        print_result("Tesseract", end_time - start_time, result_text)

    except ImportError:
        print("⚠️ 跳過測試：`pytesseract` 或 `Pillow` 套件未安裝。")
    except pytesseract.TesseractNotFoundError:
        print("❌ 錯誤：找不到 Tesseract 執行檔。")
        print("請確保 Tesseract OCR 引擎已在系統中安裝並加入 PATH。")
    except Exception as e:
        print(f"❌ 執行測試時發生錯誤: {e}")


async def main():
    """主執行函式，依序執行所有測試。"""
    print("="*60)
    print("🚀 開始本地 OCR 模型橫向評測...")
    print("="*60)

    # 執行 Ollama 方案測試
    await test_ocrflux()

    # 執行 EasyOCR 方案測試
    await test_easyocr()

    # 執行 Tesseract 方案測試
    await test_tesseract()

    print("\n🏁 所有測試執行完畢。")

if __name__ == "__main__":
    asyncio.run(main())