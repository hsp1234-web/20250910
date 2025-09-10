import json
import time
import argparse
import sys
from pathlib import Path

def main():
    """
    一個升級版的模擬 Gemini 處理器。
    它接收與真實處理器相同的彈性參數，並根據這些參數產出一個假的 .txt 或 .html 報告。
    """
    parser = argparse.ArgumentParser(description="模擬 Gemini AI 彈性處理流程。")
    # Add a command argument to handle different entry points, mirroring the real script
    parser.add_argument("--command", type=str, default="process", choices=["process", "list_models", "validate_key"])
    args, remaining_argv = parser.parse_known_args()

    # Handle non-process commands
    if args.command == "list_models":
        models_list = [
            {"id": "gemini-pro-mock", "name": "Gemini Pro (模擬)"},
            {"id": "gemini-1.5-flash-mock", "name": "Gemini 1.5 Flash (模擬)"}
        ]
        print(json.dumps(models_list), flush=True)
        sys.exit(0)

    if args.command == "validate_key":
        # In mock mode, any key is valid.
        sys.exit(0)

    # Handle the 'process' command
    process_parser = argparse.ArgumentParser()
    process_parser.add_argument("--audio-file", required=True, help="輸入的音訊檔案路徑。")
    process_parser.add_argument("--model", required=True, help="要使用的 Gemini 模型。")
    process_parser.add_argument("--video-title", required=True, help="原始影片標題。")
    process_parser.add_argument("--output-dir", required=True, help="儲存報告的目錄。")
    process_parser.add_argument("--tasks", type=str, default="summary,transcript", help="要執行的任務列表。")
    process_parser.add_argument("--output-format", type=str, default="html", choices=["html", "txt"], help="輸出的檔案格式。")

    process_args = process_parser.parse_args(remaining_argv)

    try:
        time.sleep(2) # 模擬處理時間

        output_dir = Path(process_args.output_dir)
        output_dir.mkdir(exist_ok=True)

        # Sanitize title for filename
        sanitized_title = "".join(c if c.isalnum() else "_" for c in process_args.video_title)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename_base = f"{sanitized_title[:50]}_{timestamp}_AI_Report"

        tasks_list = [t.strip() for t in process_args.tasks.split(',')]

        output_path = None

        if process_args.output_format == "html":
            # Generate mock HTML content
            tasks_html = "".join(f"<li>已完成模擬任務: {task}</li>" for task in tasks_list)
            html_content = f"""
<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="UTF-8"><title>AI 分析報告 - {process_args.video_title}</title></head>
<body>
    <h1>AI 分析報告 (模擬)</h1>
    <h2>影片標題：{process_args.video_title}</h2>
    <p>這是一份由 <b>mock_gemini_processor.py</b> 根據以下參數生成的模擬 HTML 報告：</p>
    <ul>
        <li>模型: <b>{process_args.model}</b></li>
        <li>請求的任務: <ul>{tasks_html}</ul></li>
        <li>輸出格式: <b>{process_args.output_format}</b></li>
    </ul>
</body>
</html>"""
            output_path = output_dir / f"{filename_base}.html"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html_content)

        elif process_args.output_format == "txt":
            # Generate mock TXT content
            tasks_txt = "\\n".join(f"- 已完成模擬任務: {task}" for task in tasks_list)
            txt_content = f"""AI 分析報告 (模擬)
=======================
影片標題：{process_args.video_title}
-----------------------
這是一份由 mock_gemini_processor.py 根據以下參數生成的模擬 TXT 報告：
- 模型: {process_args.model}
- 請求的任務:
{tasks_txt}
- 輸出格式: {process_args.output_format}
"""
            output_path = output_dir / f"{filename_base}.txt"
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(txt_content)

        # JULES'S FIX: Add the video_title and other missing fields to the final JSON output
        result = {
            "type": "result",
            "status": "已完成",
            "output_path": str(output_path),
            "video_title": process_args.video_title,
            "total_tokens_used": 1234,  # Mock value
            "processing_duration_seconds": 5.67,  # Mock value
            "html_report_path": str(output_path) if process_args.output_format == "html" else None,
            "txt_report_path": str(output_path) if process_args.output_format == "txt" else None
        }
        print(json.dumps(result), flush=True)
        time.sleep(0.1) # Add a small delay to ensure stdout is flushed
        sys.exit(0)

    except Exception as e:
        error_result = {
            "type": "result",
            "status": "failed",
            "error": f"模擬 Gemini 處理器發生錯誤: {e}"
        }
        print(json.dumps(error_result), flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
