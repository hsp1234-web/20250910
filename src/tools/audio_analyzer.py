
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
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = PROJECT_ROOT / "downloads" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stderr)]
)
log = logging.getLogger('audio_analyzer_tool')

def generate_combined_prompt(tasks: list) -> str:
    """
    根據任務列表動態生成一個綜合性的提示詞。
    """
    prompt_parts = []
    use_traditional_chinese = 'translate_zh' in tasks

    language_instruction = "確保所有文字都以繁體中文呈現" if use_traditional_chinese else "使用音訊的原始語言"

    prompt_parts.append(f"請根據此音訊檔案完成以下任務，並{language_instruction}：")

    task_descriptions = {
        "transcript": "1. 生成完整的逐字稿。",
        "summary": "2. 根據逐字稿，撰寫一份重點摘要。"
    }

    # 按照 transcript, summary 的順序添加任務描述
    if 'transcript' in tasks:
        prompt_parts.append(task_descriptions['transcript'])
    if 'summary' in tasks:
        prompt_parts.append(task_descriptions['summary'])

    # 如果只有逐字稿任務，且沒有要求翻譯，則遵循特殊規則
    if tasks == ['transcript']:
        return "請將此音訊檔案轉換為逐字稿，並使用其原始語言呈現。"

    formatting_instruction = "請在你的回覆中，為每個任務使用清晰的 Markdown 標題（例如：`## 逐字稿`、`## 重點摘要`）來分隔內容。"
    prompt_parts.append(formatting_instruction)

    return "\n".join(prompt_parts)


def upload_file_via_rest(file_path: Path, api_key: str) -> dict:
    """
    使用 cURL 執行檔案上傳，以繞過 SSL 問題並確保與 Gemini API 的相容性。
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

        init_url = "https://generativelanguage.googleapis.com/upload/v1beta/files"
        init_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(file_size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
            "x-goog-api-key": api_key
        }
        init_command_list = ["curl", "-sS", "-D", "-"]
        for k, v in init_headers.items():
            init_command_list.extend(["-H", f"{k}: {v}"])
        init_command_list.extend(["--data-binary", json.dumps({"file": {"display_name": display_filename}})])
        init_command_list.append(init_url)

        proc = subprocess.run(init_command_list, shell=False, capture_output=True, text=True, check=True, encoding='utf-8')

        upload_url = next((line.split(":", 1)[1].strip() for line in proc.stdout.splitlines() if "x-goog-upload-url:" in line.lower()), None)

        if not upload_url:
            raise IOError(f"❌ cURL 初始化失敗：未能在回應中找到上傳 URL。\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        log.info("✅ 步驟 1/3 完成: 已成功獲取上傳 URL。")

        upload_headers = {
            'X-Goog-Upload-Command': 'upload, finalize',
            'X-Goog-Upload-Offset': '0'
        }
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

        log.info(f"步驟 3/3: 等待伺服器處理檔案 '{file_info['name']}'...")
        get_url = f"https://generativelanguage.googleapis.com/v1beta/{file_info['name']}?key={api_key}"

        for i in range(12):  # 最多等待 60 秒
            time.sleep(5)
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
                return status_result
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
    start_time = time.time()
    total_tokens = 0

    log.info(f"開始分析檔案: {file_path}")
    log.info(f"使用模型: {model_name}")
    log.info(f"執行任務: {', '.join(tasks)}")

    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        log.error(f"API 金鑰設定失敗: {e}")
        raise ValueError("提供的 API 金鑰無效或格式不正確。")

    try:
        audio_file_info = upload_file_via_rest(file_path, api_key)
        if not audio_file_info or "name" not in audio_file_info:
            raise ValueError(f"從上傳 API 收到的回應格式不正確：缺少 'name' 欄位。回應: {audio_file_info}")
    except Exception as e:
        log.error(f"透過 REST API 上傳檔案時發生錯誤: {e}")
        raise

    model = genai.GenerativeModel(model_name=model_name)

    prompt = generate_combined_prompt(tasks)
    log.info(f"組合後的提示詞:\n---\n{prompt}\n---")

    try:
        file_for_prompt = {
            "file_data": {
                "mime_type": audio_file_info['mimeType'],
                "file_uri": audio_file_info['uri']
            }
        }
        prompt_content = [prompt, file_for_prompt]

        token_count_response = model.count_tokens(prompt_content)
        total_tokens += token_count_response.total_tokens

        response = model.generate_content(prompt_content)
        report_content = response.text

        token_count_response = model.count_tokens(report_content)
        total_tokens += token_count_response.total_tokens

        file_base_name = file_path.stem
        report_path = REPORTS_DIR / f"{file_base_name}_report.md"
        report_path.write_text(report_content, encoding='utf-8')

        output_files = [{"type": "綜合報告", "path": str(report_path)}]
        log.info(f"✅ 綜合報告已生成並儲存至 {report_path}")

    except Exception as e:
        log.error(f"生成報告時發生錯誤: {e}", exc_info=True)
        raise

    end_time = time.time()
    processing_time_seconds = round(end_time - start_time, 2)
    log.info(f"✅ 所有任務完成，總耗時: {processing_time_seconds} 秒，總 Token 數: {total_tokens}")

    final_output = {
        "status": "completed",
        "original_filename": file_path.name,
        "results": {"report_content": report_content},
        "output_files": output_files,
        "processing_time_seconds": processing_time_seconds,
        "total_tokens": total_tokens
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

    task_list = [task.strip() for task in args.tasks.split(',') if task.strip()]

    try:
        analyze_audio(file_path, args.model, task_list, args.api_key)
    except Exception as e:
        log.error(f"分析過程中發生未預期的錯誤: {e}", exc_info=True)
        print(json.dumps({"status": "failed", "error": str(e)}), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
