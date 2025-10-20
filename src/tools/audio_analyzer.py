# -*- coding: utf-8 -*-
import argparse
import json
import logging
import sys
from pathlib import Path
import google.generativeai as genai
import time
import requests
import mimetypes

# --- 常數與路徑設定 ---
REPORTS_DIR = Path("downloads/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
log = logging.getLogger('audio_analyzer_tool')

# --- 提示詞模板 ---
PROMPTS = {
    "transcript": "請將此音訊檔案轉換為逐字稿。",
    "summary": "請根據此音訊檔案的逐字稿，產生一份150-200字的重點摘要。",
    "translate_zh": "請將以下的逐字稿翻譯成流暢的繁體中文：\n\n---\n{transcript}\n---"
}

def upload_file_via_rest(file_path: Path, api_key: str) -> dict:
    """
    使用 Gemini REST API 上傳檔案，以繞過 SDK 的問題。
    """
    log.info(f"開始透過 REST API 上傳檔案: {file_path.name}")

    # 1. 獲取上傳 URI
    headers = {"X-Goog-Api-Key": api_key, "Content-Type": "application/json"}
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "application/octet-stream"

    payload = {"file": {"displayName": file_path.name, "mimeType": mime_type}}

    upload_url = f"https://generativelanguage.googleapis.com/v1beta/files"

    log.info("步驟 1/3: 正在獲取上傳 URI...")
    init_res = requests.post(upload_url, headers=headers, json=payload)
    init_res.raise_for_status()
    upload_uri = init_res.json()["file"]["uploadUri"]

    # 2. 上傳檔案內容
    log.info("步驟 2/3: 正在上傳檔案二進位內容...")
    upload_headers = {"X-Goog-Api-Key": api_key, "Content-Type": mime_type}
    with open(file_path, "rb") as f:
        upload_res = requests.put(upload_uri, headers=upload_headers, data=f)
        upload_res.raise_for_status()

    file_info = upload_res.json()["file"]
    file_uri = file_info["uri"]

    # 3. 等待檔案處理完成
    log.info("步驟 3/3: 正在等待伺服器處理檔案...")
    get_headers = {"X-Goog-Api-Key": api_key}
    while True:
        time.sleep(5)
        get_res = requests.get(f"https://generativelanguage.googleapis.com/v1beta/{file_info['name']}", headers=get_headers)
        get_res.raise_for_status()
        file_info = get_res.json()["file"]
        if file_info["state"] == "ACTIVE":
            log.info("✅ 檔案已成功上傳並處理完畢。")
            return file_info
        elif file_info["state"] == "FAILED":
            raise RuntimeError(f"REST API 檔案處理失敗: {file_info.get('error', '未知錯誤')}")

def analyze_audio(file_path: Path, model_name: str, tasks: list, api_key: str):
    """
    對指定的音訊檔案執行 AI 分析任務，並將結果存檔。
    """
    log.info(f"開始分析檔案: {file_path}")
    log.info(f"使用模型: {model_name}")
    log.info(f"執行任務: {', '.join(tasks)}")

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        log.error(f"API 金鑰設定失敗: {e}")
        raise ValueError("提供的 API 金鑰無效或格式不正確。")

    # 1. 上傳檔案 (使用新的 REST API 方式)
    try:
        audio_file_info = upload_file_via_rest(file_path, api_key)
        # 為了與 genai SDK 相容，我們需要從 REST 回應中建立一個 genai.File 物件
        audio_file = genai.get_file(name=audio_file_info["name"])
    except Exception as e:
        log.error(f"透過 REST API 上傳檔案時發生錯誤: {e}")
        raise

    # --- 任務執行 ---
    model = genai.GenerativeModel(model_name=model_name)
    results = {}
    output_files = []
    base_filename = file_path.stem

    # --- 任務一：生成逐字稿 (如果需要) ---
    transcript_text = None
    if "transcript" in tasks or "summary" in tasks or "translate_zh" in tasks:
        log.info("正在生成逐字稿...")
        try:
            response = model.generate_content([PROMPTS["transcript"], audio_file])
            transcript_text = response.text
            results["transcript"] = transcript_text

            # 將逐字稿存檔
            transcript_path = REPORTS_DIR / f"{base_filename}_transcript.txt"
            transcript_path.write_text(transcript_text, encoding='utf-8')
            output_files.append({
                "type": "逐字稿",
                "path": str(transcript_path)
            })
            log.info(f"✅ 逐字稿已生成並儲存至 {transcript_path}")

        except Exception as e:
            log.error(f"生成逐字稿時發生錯誤: {e}")
            results["transcript_error"] = str(e)

    # --- 任務二：生成摘要 (如果需要且已有逐字稿) ---
    if "summary" in tasks and transcript_text:
        log.info("正在生成摘要...")
        try:
            response = model.generate_content([PROMPTS["summary"], transcript_text])
            summary_text = response.text
            results["summary"] = summary_text

            # 將摘要存檔
            summary_path = REPORTS_DIR / f"{base_filename}_summary.md"
            summary_path.write_text(summary_text, encoding='utf-8')
            output_files.append({
                "type": "重點摘要",
                "path": str(summary_path)
            })
            log.info(f"✅ 摘要已生成並儲存至 {summary_path}")

        except Exception as e:
            log.error(f"生成摘要時發生錯誤: {e}")
            results["summary_error"] = str(e)

    # --- 任務三：翻譯 (如果需要且已有逐字稿) ---
    if "translate_zh" in tasks and transcript_text:
        log.info("正在將逐字稿翻譯成繁體中文...")
        try:
            prompt = PROMPTS["translate_zh"].format(transcript=transcript_text)
            response = model.generate_content([prompt])
            translated_text = response.text
            results["translation_zh"] = translated_text

            # 將翻譯結果存檔
            translation_path = REPORTS_DIR / f"{base_filename}_translation_zh.txt"
            translation_path.write_text(translated_text, encoding='utf-8')
            output_files.append({
                "type": "中文翻譯",
                "path": str(translation_path)
            })
            log.info(f"✅ 翻譯已生成並儲存至 {translation_path}")

        except Exception as e:
            log.error(f"翻譯時發生錯誤: {e}")
            results["translation_error"] = str(e)


    # --- 最終結果輸出 ---
    final_output = {
        "status": "completed",
        "original_filename": file_path.name,
        "results": results,
        "output_files": output_files
    }

    print(json.dumps(final_output, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description="音訊 AI 分析工具。")
    parser.add_argument("--file-path", type=str, required=True, help="要分析的音訊檔案路徑。")
    parser.add_argument("--model", type=str, required=True, help="要使用的 AI 模型名稱。")
    parser.add_argument("--tasks", type=str, required=True, help="要執行的任務列表，以逗號分隔 (例如 'transcript,summary')。")
    parser.add_argument("--api-key", type=str, required=True, help="用於驗證的 Google API 金鑰。")

    args = parser.parse_args()

    file_path = Path(args.file_path)
    if not file_path.exists():
        log.error(f"錯誤：檔案不存在 -> {file_path}")
        print(json.dumps({"status": "failed", "error": "指定的檔案不存在。"}), flush=True)
        sys.exit(1)

    task_list = [task.strip() for task in args.tasks.split(',')]

    try:
        analyze_audio(file_path, args.model, task_list, args.api_key)
    except Exception as e:
        log.error(f"分析過程中發生未預期的錯誤: {e}", exc_info=True)
        print(json.dumps({"status": "failed", "error": str(e)}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
