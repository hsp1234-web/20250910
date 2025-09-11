import sys
import json
from pathlib import Path
import google.generativeai as genai
from PIL import Image

# --- 路徑修正 ---
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.content_extractor import extract_content

def main():
    # --- PoC 參數 ---
    API_KEY = "AIzaSyBdw0gY2oh2W_r1eN3ALzK9RCAAcedgF3E"
    MODEL_NAME = "gemini-1.5-flash-latest" # Using 1.5 flash as it's a stable, recent version. 2.5 is not a real model name.
    FILE_TO_PROCESS = "poc_input.txt" # 使用我們建立的文字檔

    # 載入我們新設計的提示詞
    try:
        with open(SRC_DIR / "prompts" / "default_prompts.json", "r", encoding="utf-8") as f:
            all_prompts = json.load(f)
        poc_prompt_template = all_prompts["trading_strategy_poc_v2"]["prompt"]
        print("✅ 成功載入 PoC 提示詞。")
    except (IOError, KeyError) as e:
        print(f"❌ 無法載入 PoC 提示詞: {e}")
        return

    # 1. 讀取文件內容
    print(f"\n📄 正在從 '{FILE_TO_PROCESS}' 讀取內容...")
    if not Path(FILE_TO_PROCESS).exists():
        print(f"❌ 錯誤: 找不到檔案 '{FILE_TO_PROCESS}'。")
        return

    with open(FILE_TO_PROCESS, "r", encoding="utf-8") as f:
        text_content = f.read()
    image_paths = [] # PoC 中暫不處理圖片
    print(f"讀取到 {len(text_content)} 字元的文字。")

    # 2. 準備 API 請求
    print(f"\n🤖 正在設定 Gemini API (模型: {MODEL_NAME})...")
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(MODEL_NAME)

    # 將提取的內容填入提示詞模板
    prompt = poc_prompt_template.format(text_content=text_content)

    # 將圖片加入到請求中
    request_contents = [prompt]
    for img_path in image_paths:
        try:
            print(f"   - 正在載入圖片: {img_path}")
            img = Image.open(img_path)
            request_contents.append(img)
        except Exception as e:
            print(f"   - ⚠️ 無法載入圖片 {img_path}: {e}")

    # 3. 執行 API 呼叫
    print("\n🚀 正在發送請求給 Gemini API...")
    try:
        response = model.generate_content(request_contents)

        print("\n--- [AI 回應開始] ---")
        print(response.text)
        print("--- [AI 回應結束] ---")

        # 4. 嘗試解析 JSON 並提供分析
        try:
            # 從 AI 回應中提取純 JSON 字串
            json_text = response.text.strip().replace("```json", "").replace("```", "")
            parsed_json = json.loads(json_text)
            print("\n✅ JSON 格式有效。分析如下：")
            for key, value in parsed_json.items():
                print(f"   - {key}: {value}")
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"\n⚠️ 警告：AI 的回傳不是有效的 JSON 格式。錯誤: {e}")

    except Exception as e:
        print(f"\n❌ 呼叫 Gemini API 時發生嚴重錯誤: {e}")

if __name__ == "__main__":
    main()
