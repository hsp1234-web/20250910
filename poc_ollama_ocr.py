import ollama
import base64
from pathlib import Path
import asyncio

# --- 設定 ---
# 我們將使用 LLaVA 模型，它是一個廣泛使用的多模態模型。
# 如果您的本地 Ollama 中有其他更適合的模型，可以替換此名稱。
MODEL_NAME = 'llava:latest'
# 您的圖片檔案路徑
IMAGE_PATH = Path('test_ocr_image.png')
# 我們給予 AI 的指令
PROMPT = "請精確地、只提取這張圖片中的所有繁體中文文字，不要包含任何描述、解釋或格式化。直接輸出文字即可。"

def check_ollama_connection():
    """檢查是否能成功連接到 Ollama 服務。"""
    try:
        client = ollama.Client()
        client.list()
        print("✅ 成功連接到本地 Ollama 服務。")
        return client
    except Exception as e:
        print(f"❌ 無法連接到本地 Ollama 服務。")
        print("請確保 Ollama 正在您的系統上運行。您可以透過在終端機執行 `ollama serve` 來啟動它。")
        print(f"詳細錯誤: {e}")
        return None

async def run_ocr_poc(client: ollama.Client):
    """執行 OCR 概念驗證的核心函式。"""
    if not IMAGE_PATH.exists():
        print(f"❌ 錯誤：找不到指定的圖片檔案 '{IMAGE_PATH}'。請確保檔案存在於正確的路徑。")
        return

    print(f"\n🔍 正在讀取圖片: {IMAGE_PATH}")
    with open(IMAGE_PATH, 'rb') as image_file:
        # 將圖片轉換為 Base64 編碼，這是傳遞給 Ollama 的標準格式
        encoded_image = base64.b64encode(image_file.read()).decode('utf-8')

    print(f"🤖 正在使用模型 '{MODEL_NAME}' 進行 OCR 分析...")
    print(f"💬 提示詞: \"{PROMPT}\"")

    try:
        # 這是與 Ollama 互動的核心部分
        # 我們使用非同步的 chat 函式，以避免長時間阻塞
        response = await asyncio.to_thread(
            client.chat,
            model=MODEL_NAME,
            messages=[
                {
                    'role': 'user',
                    'content': PROMPT,
                    'images': [encoded_image]
                }
            ]
        )

        print("\n" + "="*30)
        print("🔬 OCR 辨識結果:")
        print("="*30)
        # 直接打印出模型回傳的內容
        ocr_result = response['message']['content']
        print(ocr_result)
        print("="*30)

    except Exception as e:
        print(f"\n❌ 在呼叫 Ollama 模型時發生錯誤。")
        if "model not found" in str(e):
            print(f"錯誤訊息顯示模型 '{MODEL_NAME}' 不存在。")
            print(f"您可以嘗試透過指令 `ollama pull {MODEL_NAME}` 來下載它。")
        else:
            print(f"詳細錯誤: {e}")

async def main():
    """主執行函式。"""
    print("--- Ollama 本地 OCR 能力概念驗證 (POC) ---")
    client = check_ollama_connection()
    if client:
        await run_ocr_poc(client)
    print("\n--- POC 執行完畢 ---")

if __name__ == "__main__":
    asyncio.run(main())