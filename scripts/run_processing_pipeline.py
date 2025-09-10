import os
import sys
import logging
import pprint

# --- 修正模組匯入路徑 ---
# 取得目前腳本的目錄，然後往上一層找到專案根目錄
# 再將 src 目錄加入到 Python 的搜尋路徑中
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "src")
sys.path.insert(0, SRC_DIR)

from tools.drive_downloader import download_file
from tools.pdf_parser import parse_pdf
from tools.report_generator import setup_font, generate_final_report
from tools.gemini_manager import GeminiManager

def main_pipeline():
    """
    主執行流程，串聯所有模組完成從下載到生成報告的完整任務。
    """
    print("="*60 + "\n🚀 啟動模組化處理流程\n" + "="*60)

    # --- 參數設定 ---
    API_KEY = os.environ.get("GOOGLE_API_KEY")
    if not API_KEY:
        logging.error("❌ 流程終止：請先設定 GOOGLE_API_KEY 環境變數。")
        return

    urls_to_process = {
        "lai_jie_6799": "https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing",
        "jing_que_3162": "https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0",
    }
    # 使用專案根目錄來定義路徑
    PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
    download_dir = os.path.join(PROJECT_ROOT, "downloads")
    image_dir = os.path.join(PROJECT_ROOT, "images")
    report_output_path = os.path.join(PROJECT_ROOT, "final_report.pdf")

    # --- 流程開始 ---
    print("\n[步驟 1/5] 正在檢查並設定中文字體...")
    if not setup_font():
        print("\n❌ 流程終止：中文字體安裝失敗。")
        return

    print("\n[步驟 2/5] 正在初始化 AI 核心管理器...")
    try:
        ai_manager = GeminiManager(api_keys=[{"name": "user_provided_key", "value": API_KEY}])
        print("✔️ AI 管理器初始化成功。")
    except Exception as e:
        print(f"\n❌ 流程終止：AI 管理器初始化失敗: {e}")
        return

    all_results = []
    print("\n[步驟 3/5] 開始逐一處理文件...")
    for name, url in urls_to_process.items():
        print("\n" + "="*60 + f"\n▶️  開始處理文件: {name}\n" + "="*60)

        downloaded_pdf_path = download_file(url, download_dir, f"{name}.pdf")
        if not downloaded_pdf_path:
            continue

        extracted_content = parse_pdf(downloaded_pdf_path, image_dir)
        if not extracted_content:
            continue

        print("\n[步驟 4/5] 正在進行 AI 分析...")
        text_analysis = ai_manager.analyze_text(extracted_content['text'])
        image_analyses = [ {img_path: ai_manager.describe_image(img_path)} for img_path in extracted_content['image_paths'] ]

        final_data = {
            "source_doc": name,
            "original_content": extracted_content,
            "ai_analysis": {"text_analysis": text_analysis, "image_analyses": image_analyses}
        }
        all_results.append(final_data)
        print("\n--- 分析結果預覽 ---")
        pprint.pprint(final_data)
        print("--- 預覽結束 ---")

    print("\n[步驟 5/5] 正在生成最終的 PDF 分析報告...")
    if all_results:
        # 為了示範，我們只用第一份文件的結果來生成報告
        generate_final_report(all_results[0], report_output_path)
    else:
        print("沒有任何文件成功處理，無法生成報告。")

    print("\n🎉 所有文件處理完畢！")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    main_pipeline()
