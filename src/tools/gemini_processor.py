# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_exceptions
    from google.generativeai.types import GenerationConfig
except ImportError:
    logging.warning("缺少 google-generativeai 模組，AI 分析功能將被停用。")
    genai = None
    GenerationConfig = None
    google_exceptions = None

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

# 備註：保留此區塊是為了展示如果此檔案需要作為獨立腳本執行時的範例。
# 在目前的專案架構中，此檔案主要作為模組被 Orchestrator 匯入和使用。
async def main():
    """
    提供一個命令列介面來測試 GeminiProcessor。
    """
    import argparse
    from rich.console import Console
    from rich.panel import Panel

    parser = argparse.ArgumentParser(description="非同步 Gemini 內容分析工具。")
    parser.add_argument("file_path", type=str, help="包含待分析內容的文字檔案路徑。")
    parser.add_argument("--api-key", type=str, help="Google API 金鑰 (或使用 GOOGLE_API_KEY 環境變數)。")
    parser.add_argument("--model", type=str, default="gemini-1.5-flash-latest", help="要使用的 Gemini 模型。")

    args = parser.parse_args()

    console = Console()

    api_key = args.api_key or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        console.print("[bold red]錯誤：[/bold red] 必須透過 --api-key 參數或 GOOGLE_API_KEY 環境變數提供 API 金鑰。")
        return

    try:
        with open(args.file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        console.print(f"[bold red]錯誤：[/bold red] 找不到檔案 '{args.file_path}'。")
        return
    except Exception as e:
        console.print(f"[bold red]錯誤：[/bold red] 讀取檔案時發生錯誤: {e}")
        return

    # 簡單的範例提示詞模板
    prompt_template = """
    你是一位專業的金融分析師。請閱讀以下財報文字，並以 JSON 格式回傳以下資訊：
    1. `company_name` (string): 公司名稱。
    2. `fiscal_year` (string): 財報的會計年度。
    3. `net_income` (number): 純利金額。
    4. `summary` (string): 少於 100 字的財報重點摘要。

    文章內容如下：
    ---
    {content}
    ---
    請直接回傳 JSON 物件，不要包含任何額外的解釋或 Markdown 標記。
    """

    console.print(Panel(f"正在使用模型 [bold cyan]{args.model}[/bold cyan] 分析檔案 [bold yellow]{args.file_path}[/bold yellow]...", title="[bold green]分析開始[/bold green]"))

    processor = GeminiProcessor(api_key=api_key, model_name=args.model)
    result, error = await processor.analyze_content(content, prompt_template)

    if error:
        console.print(Panel(f"分析失敗：\n[bold red]{error}[/bold red]", title="[bold red]分析失敗[/bold red]"))
    else:
        console.print(Panel(json.dumps(result, indent=2, ensure_ascii=False), title="[bold green]分析結果 (JSON)[/bold green]"))


if __name__ == "__main__":
    # 為了能從命令列執行此腳本進行測試
    import os
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # 檢查是否有名為 "GOOGLE_API_KEY" 的環境變數
    if not os.environ.get("GOOGLE_API_KEY"):
        print("警告: GOOGLE_API_KEY 環境變數未設定。如果需要，請透過 --api-key 參數提供。")

    # 在 Windows 上設定正確的事件迴圈策略
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(main())
