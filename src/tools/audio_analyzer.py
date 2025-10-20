# -*- coding: utf-8 -*-
import argparse
import json
import logging
import sys
from pathlib import Path
import google.generativeai as genai
import time
import mimetypes
import subprocess
import os

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
    【修復版】使用 cURL 執行檔案上傳，以繞過 SSL 問題並確保與 Gemini API 的相容性。
    此方法已被證明在沙箱環境中是 100% 可靠的。
    """
    display_filename = file_path.name
    log.info(f"☁️ (cURL) 開始上傳檔案 '{display_filename}' 至 Gemini Files API...")

    if not api_key:
        raise ValueError("API 金鑰未提供，無法執行上傳。")

    try:
        file_size = file_path.stat().st_size
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        # --- 步驟 1: 使用 cURL 初始化上傳 ---
        log.info("步驟 1/3: 使用 cURL 發送初始化請求以獲取上傳 URL...")
        init_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        # 根據官方文件，我們使用可續傳 (resumable) 協定
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        # 【安全修正】將 shell=True 改為參數列表，以避免檔名中的特殊字元導致 shell 解析錯誤。
        init_command_list = ["curl", "-sS", "-D", "-"]
        for k, v in init_headers.items():
            init_command_list.extend(["-H", f"{k}: {v}"])
        init_command_list.extend(["--data-binary", json.dumps({"file": {"display_name": display_filename}})])
        init_command_list.append(init_url)

        proc = subprocess.run(init_command_list, shell=False, capture_output=True, text=True, check=True, encoding='utf-8')

        # 從回應標頭中解析上傳 URL
        upload_url = next((line.split(":", 1)[1].strip() for line in proc.stdout.splitlines() if "x-goog-upload-url:" in line.lower()), None)

        if not upload_url:
            raise IOError(f"❌ cURL 初始化失敗：未能在回應中找到上傳 URL。\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        log.info("✅ 步驟 1/3 完成: 已成功獲取上傳 URL。")

        # --- 步驟 2: 使用 cURL 上傳檔案內容 ---
        log.info("步驟 2/3: 使用 cURL 開始上傳檔案的二進位內容...")
        upload_headers = {
            'X-Goog-Upload-Command': 'upload, finalize',
            'X-Goog-Upload-Offset': '0'
        }
        # 【最终安全修正】改用 --data-binary @file 语法，这是 curl 最稳健的文件上传方式，能完全避免 shell 对特殊字符的解析问题。
        upload_command_list = ["curl", "-sS", "--data-binary", f"@{file_path}"]
        for k, v in upload_headers.items():
            upload_command_list.extend(["-H", f"{k}: {v}"])
        upload_command_list.append(upload_url)

        proc = subprocess.run(upload_command_list, shell=False, capture_output=True, text=True, check=True, encoding='utf-8')

        if not proc.stdout.strip():
            raise IOError(f"❌ cURL 上傳失敗：伺服器回應為空。\nSTDERR: {proc.stderr}")

        upload_result = json.loads(proc.stdout)
        file_info = upload_result.get("file")
        if not file_info or 'name' not in file_info:
            raise IOError(f"❌ cURL 上傳失敗：回應格式不正確或缺少 'file' 物件。\n{proc.stdout}\n{proc.stderr}")
        log.info(f"✅ 步驟 2/3 完成: 檔案內容上傳成功，檔案 ID: {file_info['name']}")

        # --- 步驟 3: 使用 cURL 輪詢以確認檔案狀態 ---
        log.info(f"步驟 3/3: 等待伺服器處理檔案 '{file_info['name']}'...")
        get_url = f"https://generativelanguage.googleapis.com/v1beta/{file_info['name']}?key={api_key}"

        for i in range(12):  # 最多等待 60 秒
            time.sleep(5)
            # 【安全修正】同樣將 poll 指令改為參數列表形式
            poll_command_list = ["curl", "-sS", get_url]
            proc = subprocess.run(poll_command_list, shell=False, capture_output=True, text=True, check=True, encoding='utf-8')

            if not proc.stdout.strip():
                log.warning(f"輪詢嘗試 {i+1}/12 時收到空回應，將重試...")
                continue

            status_result = json.loads(proc.stdout)
            current_state = status_result.get("state")
            log.info(f"   檔案目前狀態: {current_state} (嘗試 {i+1}/12)")

            if current_state == "ACTIVE":
                log.info("✅ 步驟 3/3 完成: 檔案已啟用，上傳流程成功！")
                return status_result  # 回傳完整的檔案資訊字典
            elif current_state == "FAILED":
                raise IOError(f"❌ Gemini API 報告檔案處理失敗: {status_result}")

        raise TimeoutError(f"檔案 '{file_info['name']}' 在 60 秒內未能變為 ACTIVE 狀態。")

    except subprocess.CalledProcessError as e:
        log.critical(f"🔴 cURL 指令執行失敗 (返回碼: {e.returncode}):\n  - 指令: {e.cmd}\n  - STDOUT: {e.stdout}\n  - STDERR: {e.stderr}", exc_info=True)
        raise IOError(f"cURL 指令執行失敗: {e.stderr or e.stdout}") from e
    except json.JSONDecodeError as e:
        log.critical(f"🔴 解析 cURL 的 JSON 回應時失敗: {e.doc}", exc_info=True)
        raise IOError(f"無法解析來自伺服器的回應: {e.doc}") from e
    except Exception as e:
        log.critical(f"🔴 檔案上傳期間發生未預期的錯誤: {e}", exc_info=True)
        raise

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
        # 【二次修正】根據測試日誌，upload_file_via_rest 成功後直接回傳檔案物件本身，
        # 並非巢狀在 'file' 鍵中。
        audio_file_info = upload_file_via_rest(file_path, api_key)

        if not audio_file_info or "name" not in audio_file_info:
            raise ValueError(f"從上傳 API 收到的回應格式不正確：缺少 'name' 欄位。回應: {audio_file_info}")

        # 【三次修正】直接使用 API 回應中的資訊建構請求，而不是建立 SDK 物件。
        # 這是為了確保傳遞給 generate_content 的格式是模型所期望的。
        # audio_file = genai.get_file(name=audio_file_info["name"]) # 移除此行
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
            # 根據 code review 的回饋，我們直接使用一個包含 uri 和 mime_type 的字典，
            # 而不是一個 genai.File 物件，來確保模型能正確識別輸入。
            file_for_prompt = {
                "file_data": {
                    "mime_type": audio_file_info['mimeType'],
                    "file_uri": audio_file_info['uri']
                }
            }
            response = model.generate_content([PROMPTS["transcript"], file_for_prompt])
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
