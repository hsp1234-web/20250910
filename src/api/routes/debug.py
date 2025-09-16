# src/api/routes/debug.py
import logging
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from core import key_manager
from tools.gemini_manager import GeminiManager

# --- 常數與設定 ---
log = logging.getLogger(__name__)
router = APIRouter()

# --- API 端點 ---

@router.post("/trigger_gemini_call", summary="[僅供測試] 觸發一次 Gemini 呼叫")
async def trigger_gemini_call(model_name: str = "Gemini 2.5 Pro"):
    """
    一個僅供端到端 (E2E) 測試使用的端點。
    它會初始化一個 GeminiManager 並執行一次簡單的文字請求，
    以便我們測試流量控制、金鑰輪換和費用追蹤等功能。
    """
    try:
        # 1. 初始化 Gemini Manager
        valid_keys = key_manager.get_all_valid_keys_for_manager()
        if not valid_keys:
            raise HTTPException(status_code=500, detail="在金鑰池中找不到任何有效的 API 金鑰。")

        # 在測試時，使用較短的超時以加速失敗判斷
        gemini = GeminiManager(api_keys=valid_keys, timeout=30)

        # 2. 執行一個虛擬的 AI 請求
        # 在真實的 E2E 測試中，gemini_manager 內部會因為找不到真實金鑰而失敗，
        # 但這已足以測試到我們想要的功能（如流量控制閥）。
        # 在有 mock server 的情況下，這裡會實際成功。
        # 為了讓測試能繼續，我們期望它最終會失敗，但這是在我們的預期之內。
        dummy_prompt = "這是一個測試提示詞，請回覆 'ok'。"
        result, error, used_key, token_usage = gemini.prompt_for_text(
            prompt=dummy_prompt,
            model_name=model_name
        )

        # 3. 記錄 token 使用量 (如果成功)
        if error is None:
            if used_key and token_usage is not None and token_usage > 0:
                key_manager.record_token_usage(key_name=used_key, tokens_used=token_usage)
            return {"status": "success", "used_key": used_key, "token_usage": token_usage, "result": result}
        else:
            # 在 E2E 測試中，我們預期會因為金鑰無效而走到這裡
            log.warning(f"測試端點中的 Gemini 呼叫按預期失敗: {error}")
            # 即使失敗，我們仍回傳 200 OK，因為觸發本身是成功的
            # 測試腳本會驗證流量控制是否生效，而不是 API 是否成功
            return {"status": "call_attempted_and_failed_as_expected", "error": str(error)}

    except Exception as e:
        log.error(f"執行測試端點時發生未預期的錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"伺服器內部錯誤: {e}")
