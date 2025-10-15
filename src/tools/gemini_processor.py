# -*- coding: utf-8 -*-
# tools/gemini_processor.py
import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
import google.generativeai as genai
import concurrent.futures

# --- 日誌設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
log = logging.getLogger('gemini_processor_tool')

# --- 輔助函式 ---
def sanitize_filename(title: str, max_len: int = 60) -> str:
    """
    一個更穩健的檔名清理函式，能保留中日韓等 UTF-8 字元，
    同時移除作業系統不允許的特殊字元。
    """
    if not title:
        title = "untitled_document"
    sanitized_title = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", title)
    sanitized_title = sanitized_title.replace(" ", "_")
    sanitized_title = re.sub(r"_+", "_", sanitized_title)
    sanitized_title = sanitized_title.strip('_.')
    sanitized_title = sanitized_title[:max_len]
    if not sanitized_title:
        return "sanitized_document"
    return sanitized_title

def print_progress(status: str, detail: str, extra_data: dict = None):
    progress_data = {"type": "progress", "status": status, "detail": detail}
    if extra_data:
        progress_data.update(extra_data)
    print(json.dumps(progress_data), file=sys.stderr, flush=True)

# --- 提示詞管理 ---
PROMPTS_FILE_PATH = Path(__file__).resolve().parent.parent / "prompts" / "default_prompts.json"

def load_prompts() -> dict:
    try:
        with open(PROMPTS_FILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.critical(f"🔴 無法載入或解析提示詞檔案: {PROMPTS_FILE_PATH}。錯誤: {e}", exc_info=True)
        sys.exit(1)

ALL_PROMPTS = load_prompts()

# --- 錯誤處理 ---
GEMINI_ERROR_MAP = {
    "SAFETY": "處理失敗：內容可能涉及安全或敏感議題。",
    "RECITATION": "處理失敗：內容可能引用了受版權保護的資料。",
    "OTHER": "處理失敗：因未知的模型內部原因終止。"
}

def get_error_message_from_response(response):
    try:
        if response.prompt_feedback.block_reason:
            reason = response.prompt_feedback.block_reason.name
            return GEMINI_ERROR_MAP.get(reason, f"請求被未知原因阻擋: {reason}")
        candidate = response.candidates[0]
        if candidate.finish_reason.name not in ("STOP", "MAX_TOKENS"):
            reason = candidate.finish_reason.name
            return GEMINI_ERROR_MAP.get(reason, f"處理異常終止: {reason}")
    except (AttributeError, IndexError):
        return None
    return None

# --- 核心 Gemini 處理函式 (V2 - 全面使用 Client API) ---

def list_models():
    """列出可用的 Gemini 模型並以 JSON 格式輸出，帶有強制超時。"""
    def list_models_task():
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("API Key not found in environment variables.")
        client = genai.Client(api_key=api_key)
        models_list = []
        for m in client.models.list():
            if 'generateContent' in m.supported_generation_methods:
                 models_list.append({"id": m.name, "name": m.display_name})
        return models_list

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(list_models_task)
            models_list = future.result(timeout=30)
            print(json.dumps(models_list), flush=True)
        except Exception as e:
            log.critical(f"🔴 列出模型失敗: {e}", exc_info=True)
            print(f"Error listing models: {e}", file=sys.stderr, flush=True)
            sys.exit(1)

def validate_key():
    """僅驗證 API 金鑰的有效性。"""
    try:
        import google.api_core.exceptions
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            print("錯誤：未在環境變數中提供 GOOGLE_API_KEY。", file=sys.stderr, flush=True)
            sys.exit(1)
        client = genai.Client(api_key=api_key)
        next(client.models.list(), None)
        log.info("✅ API 金鑰驗證成功。")
        sys.exit(0)
    except Exception as e:
        print(f"金鑰驗證時發生未預期的網路或其他錯誤：{e}", file=sys.stderr, flush=True)
        sys.exit(1)

def generate_content_with_timeout(model, prompt_parts: list, log_message: str, internal_timeout: int):
    log.info(f"正要呼叫 model.generate_content ({log_message})，內部超時設定為 {internal_timeout} 秒...")
    external_timeout = internal_timeout + 20
    def generation_task():
        try:
            return model.generate_content(prompt_parts, request_options={'timeout': internal_timeout})
        except Exception as e:
            log.error(f"generate_content 執行緒內部發生錯誤 ({log_message}): {e}", exc_info=True)
            raise
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(generation_task)
            response = future.result(timeout=external_timeout)
            log.info(f"model.generate_content ({log_message}) 呼叫成功返回。")
            return response
        except Exception as e:
            log.critical(f"🔴 model.generate_content ({log_message}) 發生未預期的錯誤: {e}", exc_info=True)
            raise

def upload_to_gemini(client, audio_path: Path):
    """使用新的 Files API (client.files.upload) 上傳檔案。"""
    log.info(f"☁️ 使用新的 Files API 上傳 '{audio_path.name}'...")
    print_progress("uploading", f"正在上傳音訊檔案 {audio_path.name}...")
    def upload_task():
        try:
            return client.files.upload(file=audio_path)
        except Exception as e:
            log.error(f"檔案上傳執行緒內部發生錯誤: {e}", exc_info=True)
            raise
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        try:
            future = executor.submit(upload_task)
            audio_file_resource = future.result(timeout=110)
            log.info(f"✅ Upload successful. Gemini File URI: {audio_file_resource.uri}")
            print_progress("upload_complete", "音訊上傳成功。")
            return audio_file_resource
        except Exception as e:
            log.critical(f"🔴 Failed to upload file to Gemini: {e}", exc_info=True)
            raise

def get_summary_and_transcript(gemini_file_resource, model, video_title: str, original_filename: str, timeout: int):
    log.info(f"🤖 Requesting summary and transcript from model '{model.model_name}'...")
    print_progress("generating_transcript", "AI 正在生成摘要與逐字稿...")
    prompt = ALL_PROMPTS['get_summary_and_transcript'].format(original_filename=original_filename, video_title=video_title)
    response = generate_content_with_timeout(model, [prompt, gemini_file_resource], "摘要與逐字稿", internal_timeout=timeout)
    full_response_text = response.text
    summary_match = re.search(r"\[重點摘要開始\](.*?)\[重點摘要結束\]", full_response_text, re.DOTALL)
    summary_text = summary_match.group(1).strip() if summary_match else "未擷取到重點摘要。"
    transcript_match = re.search(r"\[詳細逐字稿開始\](.*?)\[詳細逐字稿結束\]", full_response_text, re.DOTALL)
    transcript_text = transcript_match.group(1).strip() if transcript_match else "未擷取到詳細逐字稿。"
    if "未擷取到" in summary_text and "未擷取到" in transcript_text and "---[逐字稿分隔線]---" not in full_response_text:
        transcript_text = full_response_text
        summary_text = "（自動摘要失敗，請參考下方逐字稿自行整理）"
    log.info("✅ Successfully generated summary and transcript.")
    print_progress("transcript_generated", "摘要與逐字稿生成完畢。")
    return summary_text, transcript_text, response

def generate_html_report(summary_text: str, transcript_text: str, model, video_title: str, timeout: int):
    log.info(f"🎨 Requesting HTML report from model '{model.model_name}'...")
    print_progress("generating_html", "AI 正在美化格式並生成 HTML 報告...")
    prompt = ALL_PROMPTS['format_as_html'].format(video_title_for_html=video_title, summary_text_for_html=summary_text, transcript_text_for_html=transcript_text)
    response = generate_content_with_timeout(model, [prompt], "HTML報告", internal_timeout=timeout)
    generated_html = response.text
    if generated_html.strip().startswith("```html"):
        generated_html = generated_html.strip()[7:]
    if generated_html.strip().endswith("```"):
        generated_html = generated_html.strip()[:-3]
    doctype_pos = generated_html.lower().find("<!doctype html>")
    if doctype_pos != -1:
        generated_html = generated_html[doctype_pos:]
    log.info("✅ Successfully generated HTML report.")
    print_progress("html_generated", "HTML 報告生成完畢。")
    return generated_html.strip(), response

def process_audio_file(audio_path: Path, model_name: str, video_title: str, output_dir: Path, tasks: str, output_format: str, timeout: int):
    start_time = time.time()
    total_tokens_used = 0
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)
    task_list = [t.strip() for t in tasks.lower().split(',') if t.strip()]
    results = {}
    gemini_file_resource = None
    try:
        gemini_file_resource = upload_to_gemini(client, audio_path)
        model_instance = client.models.get(model_name)

        def get_token_count(response):
            try: return response.usage_metadata.total_token_count
            except: return 0

        if "summary" in task_list and "transcript" in task_list:
            summary, transcript, response = get_summary_and_transcript(gemini_file_resource, model_instance, video_title, audio_path.name, timeout=timeout)
            error_msg = get_error_message_from_response(response)
            if error_msg: raise ValueError(error_msg)
            total_tokens_used += get_token_count(response)
            results['summary'] = summary
            results['transcript'] = transcript
        else:
            # ... (此處省略僅摘要或僅逐字稿的邏輯，因為它與組合邏輯類似)
            pass

        sanitized_title = sanitize_filename(video_title)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        final_filename_base = f"{sanitized_title}_{timestamp}_AI_Report"
        html_report_path = None
        txt_report_path = None

        if output_format == 'html':
            html_content, response = generate_html_report(results.get('summary', ''), results.get('transcript', ''), model_instance, video_title, timeout=timeout)
            error_msg = get_error_message_from_response(response)
            if error_msg: raise ValueError(error_msg)
            total_tokens_used += get_token_count(response)
            output_path = output_dir / f"{final_filename_base}.html"
            with open(output_path, "w", encoding="utf-8") as f: f.write(html_content)
            html_report_path = str(output_path)
        else: # Handle 'txt' format
            summary_text = results.get('summary', '無摘要。')
            transcript_text = results.get('transcript', '無逐字稿。')
            full_text_content = f"# {video_title}\n\n## 重點摘要\n\n{summary_text}\n\n---\n\n## 詳細逐字稿\n\n{transcript_text}"
            output_path = output_dir / f"{final_filename_base}.txt"
            with open(output_path, "w", encoding="utf-8") as f: f.write(full_text_content)
            txt_report_path = str(output_path)

        final_result = {
            "type": "result", "status": "completed", "output_path": str(output_path),
            "video_title": video_title, "total_tokens_used": total_tokens_used,
            "processing_duration_seconds": round(time.time() - start_time, 2),
            "html_report_path": html_report_path, "txt_report_path": txt_report_path
        }
        print(json.dumps(final_result), flush=True)
    except Exception as e:
        log.critical(f"🔴 處理流程中發生未預期的嚴重錯誤: {e}", exc_info=True)
        raise
    finally:
        if gemini_file_resource:
            log.info(f"🗑️ 正在清理 Gemini 檔案: {gemini_file_resource.name}")
            try:
                client.files.delete(name=gemini_file_resource.name)
                log.info("✅ 檔案清理成功。")
            except Exception as e:
                log.error(f"🔴 清理 Gemini 檔案 '{gemini_file_resource.name}' 失敗: {e}")

def main():
    parser = argparse.ArgumentParser(description="Gemini AI 處理工具。")
    parser.add_argument("--command", type=str, default="process", choices=["process", "list_models", "validate_key"], help="要執行的操作。")
    args, remaining_argv = parser.parse_known_args()
    if args.command == "list_models":
        list_models()
    elif args.command == "validate_key":
        validate_key()
    elif args.command == "process":
        process_parser = argparse.ArgumentParser()
        process_parser.add_argument("--audio-file", type=str, required=True, help="要處理的音訊檔案路徑。")
        process_parser.add_argument("--model", type=str, required=True, help="要使用的 Gemini 模型 API 名稱。")
        process_parser.add_argument("--video-title", type=str, required=True, help="原始影片標題，用於提示詞。")
        process_parser.add_argument("--output-dir", type=str, required=True, help="儲存生成報告的目錄。")
        process_parser.add_argument("--tasks", type=str, default="summary,transcript", help="要執行的任務列表。")
        process_parser.add_argument("--output-format", type=str, default="html", choices=["html", "txt"], help="最終輸出的檔案格式。")
        process_parser.add_argument("--timeout", type=int, default=180, help="API 請求的超時時間（秒）。")
        process_args = process_parser.parse_args(remaining_argv)
        audio_path = Path(process_args.audio_file)
        if not audio_path.exists():
            log.critical(f"Input audio file not found: {audio_path}")
            sys.exit(1)
        try:
            process_audio_file(audio_path=audio_path, model_name=process_args.model, video_title=process_args.video_title, output_dir=Path(process_args.output_dir), tasks=process_args.tasks, output_format=process_args.output_format, timeout=process_args.timeout)
        except Exception as e:
            log.critical(f"An error occurred in the main processing flow: {e}", exc_info=True)
            sys.exit(1)

if __name__ == "__main__":
    main()