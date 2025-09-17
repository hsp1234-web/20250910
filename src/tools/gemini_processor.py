# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, Optional, Tuple, List

# --- 路徑修正 ---
# 確保即使從命令列執行，也能找到 src 目錄
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
    from google.generativeai.types import GenerationConfig
    from tools.transcriber import Transcriber  # 匯入我們自己的轉錄器
except ImportError as e:
    logging.warning(f"缺少必要的模組 ({e})，AI 分析功能可能受限。")
    genai = None
    GenerationConfig = None
    google_exceptions = None
    Transcriber = None

# 專為此模組設定日誌
log = logging.getLogger(__name__)


class GeminiProcessor:
    """
    一個使用 asyncio 實現的非同步 Gemini API 處理器。
    它被設計為由 Orchestrator 在受控的併發環境中呼叫。
    """

    def __init__(self, api_key: str, model_name: str = "gemini-1.5-flash-latest", timeout: int = 120):
        """
        初始化 Gemini 處理器。

        Args:
            api_key (str): 用於此次操作的 Google API 金鑰。
            model_name (str): 要使用的 Gemini 模型名稱。
            timeout (int): API 請求的網路超時時間（秒）。
        """
        if not genai:
            raise ImportError("GeminiProcessor 無法初始化，因為 google.generativeai 模組未安裝。")

        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout
        self.model = None # 模型將在首次需要時配置

    def _configure_model(self) -> None:
        """設定 genai 模組和模型實例。"""
        if self.model is None:
            genai.configure(api_key=self.api_key)
            generation_config = GenerationConfig(response_mime_type="application/json")
            self.model = genai.GenerativeModel(
                self.model_name,
                generation_config=generation_config
            )

    async def _call_gemini_api(self, prompt: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        以非同步方式呼叫 Gemini API。
        使用 asyncio.to_thread 來執行會阻塞的 SDK 呼叫。

        Args:
            prompt (str): 發送給模型的提示詞。

        Returns:
            一個元組 (結果, 錯誤訊息)。
            - result (dict | None): 成功時為解析後的 JSON 物件。
            - error (str | None): 失敗時為錯誤訊息字串。
        """
        try:
            self._configure_model()

            # 將阻塞的 SDK 呼叫移至背景執行緒
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                request_options={'timeout': self.timeout}
            )

            raw_text = response.text
            # 移除常見的 markdown 程式碼區塊標記
            if raw_text.strip().startswith("```json"):
                raw_text = raw_text.strip()[7:-3].strip()

            return json.loads(raw_text), None

        except json.JSONDecodeError as e:
            log.error(f"JSON 解碼失敗: {e}\n收到的原始文字: '{raw_text}'")
            return None, f"JSON 解碼失敗: {e}"
        except Exception as e:
            # 處理 Google API 的特定錯誤
            if isinstance(e, google_exceptions.ResourceExhausted):
                log.error(f"API 配額耗盡: {e}")
                return None, "API_RATE_LIMIT_EXCEEDED"

            log.error(f"呼叫 Gemini API 時發生未預期的錯誤: {e}", exc_info=True)
            return None, str(e)

    async def analyze_content(self, content: str, prompt_template: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        根據提供的內容和提示詞模板進行分析。

        Args:
            content (str): 要分析的文字內容。
            prompt_template (str): 用於生成最終提示詞的模板。

        Returns:
            一個元組 (分析結果, 錯誤訊息)。
        """
        prompt = prompt_template.format(content=content)
        log.info(f"準備使用模型 '{self.model_name}' 進行內容分析...")

        result, error = await self._call_gemini_api(prompt)

        if error:
            log.error(f"內容分析失敗: {error}")
            return None, error

        log.info("內容分析成功完成。")
        return result, None

# --- 命令列介面 (CLI) 輔助函式 ---

def _validate_key(api_key: str) -> bool:
    """
    透過嘗試列出模型來驗證 API 金鑰的有效性。
    這是一個輕量級的操作，足以確認金鑰是否有效。
    """
    try:
        genai.configure(api_key=api_key)
        # 列出模型是一個相對快速且低成本的驗證方法
        list(genai.list_models())
        return True
    except Exception as e:
        # 捕獲所有可能的例外，例如權限錯誤、格式錯誤等
        log.error(f"金鑰驗證失敗: {e}")
        return False

def _list_models(api_key: str) -> List[Dict[str, str]]:
    """
    獲取所有可用的生成模型列表。
    """
    try:
        genai.configure(api_key=api_key)
        models = [
            {"id": m.name, "name": m.display_name}
            for m in genai.list_models()
            if 'generateContent' in m.supported_generation_methods
        ]
        return models
    except Exception as e:
        log.error(f"獲取模型列表時發生錯誤: {e}")
        # 以防萬一，回傳一個空列表
        return []

def _generate_report_from_transcript(transcript: str, video_title: str, tasks: str, model: str, api_key: str) -> str:
    """
    根據逐字稿生成摘要或執行其他 AI 任務。
    """
    # 這裡可以根據 `tasks` 參數擴充更多功能
    # 目前僅實作摘要
    prompt = f"""
你是一個專業的報告分析師。
這是一段來自 YouTube 影片的逐字稿，影片標題是「{video_title}」。
請根據以下逐字稿，生成一份包含「摘要」和「重點」的報告。

逐字稿內容：
---
{transcript}
---

請以 JSON 格式輸出，包含以下欄位：
- "summary": (string) 影片內容的簡潔摘要。
- "highlights": (list of strings) 條列式的重點。
"""
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(model)
    response = gemini_model.generate_content(prompt)
    return response.text


async def main():
    """
    提供一個命令列介面來執行不同的 Gemini 相關任務。
    """
    import argparse
    import pathlib

    parser = argparse.ArgumentParser(description="Gemini 處理工具。")
    parser.add_argument(
        "--command",
        type=str,
        required=True,
        choices=['validate_key', 'list_models', 'process'],
        help="要執行的命令。"
    )
    parser.add_argument("--api-key", type=str, help="Google API 金鑰 (或使用 GOOGLE_API_KEY 環境變數)。")
    parser.add_argument("--model", type=str, default="gemini-1.5-flash-latest", help="要使用的 Gemini 模型。")
    parser.add_argument("--audio-file", type=str, help="要處理的音訊檔案路徑 (僅 'process' 命令需要)。")
    parser.add_argument("--output-dir", type=str, default=".", help="報告和逐字稿的輸出目錄。")
    parser.add_argument("--video-title", type=str, default="未命名影片", help="影片的標題。")
    parser.add_argument("--tasks", type=str, default="summary,transcript", help="要執行的任務列表，以逗號分隔。")
    parser.add_argument("--output-format", type=str, default="html", choices=['html', 'txt'], help="報告的輸出格式。")


    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GOOGLE_API_KEY")
    if not api_key and args.command != 'process':
        # 對於 process 命令，金鑰可能在 payload 中提供，所以這裡不立即退出
        print(json.dumps({"error": "API Key not found", "error_code": "API_KEY_MISSING"}), file=sys.stderr)
        sys.exit(1)

    # --- 根據命令執行對應的邏輯 ---

    if args.command == "validate_key":
        if _validate_key(api_key):
            print("金鑰驗證成功。")
            sys.exit(0)
        else:
            print("金鑰驗證失敗。", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list_models":
        models = _list_models(api_key)
        if models:
            print(json.dumps(models, ensure_ascii=False))
            sys.exit(0)
        else:
            print("無法獲取模型列表。", file=sys.stderr)
            sys.exit(1)

    elif args.command == "process":
        if not args.audio_file:
            print(json.dumps({"error": "audio_file is required for process command"}), file=sys.stderr)
            sys.exit(1)
        if not Transcriber:
            print(json.dumps({"error": "Transcriber module not available"}), file=sys.stderr)
            sys.exit(1)

        output_dir = pathlib.Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        transcript_path = output_dir / f"{pathlib.Path(args.audio_file).stem}_transcript.txt"

        try:
            # 步驟 1: 轉錄音訊檔案
            print(f"開始轉錄音訊檔案: {args.audio_file}...")
            transcriber = Transcriber(model_size='base') # JULES-FIX-26.22-Hotfix: 使用正確的參數 'model_size'
            transcript_text = await transcriber.transcribe_audio(args.audio_file)
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            print(f"逐字稿已儲存至: {transcript_path}")

            # 步驟 2: 根據逐字稿生成報告
            print("開始生成 AI 報告...")
            report_content = _generate_report_from_transcript(
                transcript=transcript_text,
                video_title=args.video_title,
                tasks=args.tasks,
                model=args.model,
                api_key=api_key
            )
            print("AI 報告生成完畢。")

            # 步驟 3: 儲存報告
            report_path = output_dir / f"{pathlib.Path(args.audio_file).stem}_report.{args.output_format}"
            with open(report_path, "w", encoding="utf-8") as f:
                # 簡單處理，未來可擴充為 HTML 模板
                f.write(report_content)
            print(f"報告已儲存至: {report_path}")

            # 最終輸出 JSON 結果給呼叫者
            final_result = {
                "status": "success",
                "output_path": str(report_path),
                "transcript_path": str(transcript_path),
                "video_title": args.video_title
            }
            print(json.dumps(final_result, ensure_ascii=False))
            sys.exit(0)

        except Exception as e:
            log.error(f"處理程序中發生錯誤: {e}", exc_info=True)
            print(json.dumps({"error": str(e)}), file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 使用 try-except 區塊來確保即使發生錯誤，也能正常退出
    try:
        asyncio.run(main())
    except SystemExit as e:
        # 捕捉 sys.exit()，這是正常的退出方式
        sys.exit(e.code)
    except Exception as e:
        # 捕捉其他未預期的錯誤
        print(json.dumps({"error": f"未預期的腳本錯誤: {e}"}), file=sys.stderr)
        sys.exit(1)
