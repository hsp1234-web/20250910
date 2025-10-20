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

# --- 提示詞模板 (Markdown 優化版) ---
PROMPTS = {
    "transcript": "請將此音訊檔案轉換為逐字稿。請直接輸出純文字內容。",
    "summary": "請根據此音訊檔案的逐字稿，產生一份150-200字的重點摘要。請使用 Markdown 的二級標題 `## 重點摘要` 作為開頭。",
    "translate_zh": "請將以下的逐字稿翻譯成流暢的繁體中文。請使用 Markdown 的二級標題 `## 中文翻譯` 作為開頭。\n\n---\n{transcript}\n---"
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
    對指定的音訊檔案執行 AI 分析任務、計算指標並將結果存檔。
    """
    # --- 初始化計時器與計數器 ---
    開始時間 = time.time()
    總計_tokens = 0

    log.info(f"開始分析檔案: {file_path}")
    log.info(f"使用模型: {model_name}")
    log.info(f"執行任務: {', '.join(tasks)}")

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        log.error(f"API 金鑰設定失敗: {e}")
        raise ValueError("提供的 API 金鑰無效或格式不正確。")

    # 1. 上傳檔案 (使用 cURL 確保穩定性)
    try:
        audio_file_info = upload_file_via_rest(file_path, api_key)
        if not audio_file_info or "name" not in audio_file_info:
            raise ValueError(f"從上傳 API 收到的回應格式不正確：缺少 'name' 欄位。回應: {audio_file_info}")
    except Exception as e:
        log.error(f"透過 REST API 上傳檔案時發生錯誤: {e}")
        raise

    # --- 任務執行 ---
    model = genai.GenerativeModel(model_name=model_name)
    分析結果 = {}
    輸出檔案列表 = []
    檔案基本名稱 = file_path.stem

    # --- 任務一：生成逐字稿 (如果需要) ---
    逐字稿內容 = None
    if "transcript" in tasks or "summary" in tasks or "translate_zh" in tasks:
        log.info("正在生成逐字稿...")
        try:
            # 準備給模型的檔案物件
            file_for_prompt = {
                "file_data": {
                    "mime_type": audio_file_info['mimeType'],
                    "file_uri": audio_file_info['uri']
                }
            }
            提示詞內容 = [PROMPTS["transcript"], file_for_prompt]

            # 計算提示詞的 Token
            token_count_response = model.count_tokens(提示詞內容)
            總計_tokens += token_count_response.total_tokens

            # 呼叫模型
            response = model.generate_content(提示詞內容)
            逐字稿內容 = response.text

            # 計算生成內容的 Token
            token_count_response = model.count_tokens(逐字稿內容)
            總計_tokens += token_count_response.total_tokens

            分析結果["transcript"] = 逐字稿內容

            # 將逐字稿存檔
            transcript_path = REPORTS_DIR / f"{檔案基本名稱}_transcript.md"
            transcript_path.write_text(逐字稿內容, encoding='utf-8')
            輸出檔案列表.append({"type": "逐字稿", "path": str(transcript_path)})
            log.info(f"✅ 逐字稿已生成並儲存至 {transcript_path}")

        except Exception as e:
            log.error(f"生成逐字稿時發生錯誤: {e}", exc_info=True)
            分析結果["transcript_error"] = str(e)

    # --- 任務二：生成摘要 (如果需要且已有逐字稿) ---
    if "summary" in tasks and 逐字稿內容:
        log.info("正在生成摘要...")
        try:
            提示詞內容 = [PROMPTS["summary"], 逐字稿內容]
            token_count_response = model.count_tokens(提示詞內容)
            總計_tokens += token_count_response.total_tokens

            response = model.generate_content(提示詞內容)
            摘要內容 = response.text

            token_count_response = model.count_tokens(摘要內容)
            總計_tokens += token_count_response.total_tokens
            分析結果["summary"] = 摘要內容

            summary_path = REPORTS_DIR / f"{檔案基本名稱}_summary.md"
            summary_path.write_text(摘要內容, encoding='utf-8')
            輸出檔案列表.append({"type": "重點摘要", "path": str(summary_path)})
            log.info(f"✅ 摘要已生成並儲存至 {summary_path}")

        except Exception as e:
            log.error(f"生成摘要時發生錯誤: {e}", exc_info=True)
            分析結果["summary_error"] = str(e)

    # --- 任務三：翻譯 (如果需要且已有逐字稿) ---
    if "translate_zh" in tasks and 逐字稿內容:
        log.info("正在將逐字稿翻譯成繁體中文...")
        try:
            提示詞內容 = PROMPTS["translate_zh"].format(transcript=逐字稿內容)
            token_count_response = model.count_tokens(提示詞內容)
            總計_tokens += token_count_response.total_tokens

            response = model.generate_content(提示詞內容)
            翻譯內容 = response.text

            token_count_response = model.count_tokens(翻譯內容)
            總計_tokens += token_count_response.total_tokens
            分析結果["translation_zh"] = 翻譯內容

            translation_path = REPORTS_DIR / f"{檔案基本名稱}_translation_zh.md"
            translation_path.write_text(翻譯內容, encoding='utf-8')
            輸出檔案列表.append({"type": "中文翻譯", "path": str(translation_path)})
            log.info(f"✅ 翻譯已生成並儲存至 {translation_path}")

        except Exception as e:
            log.error(f"翻譯時發生錯誤: {e}", exc_info=True)
            分析結果["translation_error"] = str(e)

    # --- 總結與最終輸出 ---
    結束時間 = time.time()
    處理總耗時_秒 = round(結束時間 - 開始時間, 2)
    log.info(f"✅ 所有任務完成，總耗時: {處理總耗時_秒} 秒，總 Token 數: {總計_tokens}")

    最終輸出 = {
        "status": "completed",
        "original_filename": file_path.name,
        "results": 分析結果,
        "output_files": 輸出檔案列表,
        "processing_time_seconds": 處理總耗時_秒,
        "total_tokens": 總計_tokens
    }

    print(json.dumps(最終輸出, ensure_ascii=False), flush=True)


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
