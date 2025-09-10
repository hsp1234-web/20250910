# src/core/rendering.py
"""
此模組提供後端渲染相關的輔助函式。
"""
from fastapi.templating import Jinja2Templates
from pathlib import Path
import logging

log = logging.getLogger(__name__)

try:
    # --- 路徑與樣板設定 ---
    # 假設此檔案位於 src/core/rendering.py
    # 樣板目錄位於 src/static/
    SRC_DIR = Path(__file__).resolve().parent.parent
    templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
    log.info("渲染模組的 Jinja2 樣板引擎初始化成功。")
except Exception as e:
    log.error(f"渲染模組初始化失敗: {e}", exc_info=True)
    # 提供一個備用的空樣板物件，避免整個應用程式啟動失敗
    templates = None

def render_processed_file_item(file_data: dict) -> str:
    """
    使用 Jinja2 樣板，渲染單個已處理檔案的 HTML 項目。

    Args:
        file_data (dict): 包含單個檔案資訊的字典。
                          預期應有 'id' 和 'display_name' 鍵。

    Returns:
        str: 渲染完成的 HTML 字串。如果樣板引擎未成功初始化，
             則回傳一個錯誤訊息的 HTML。
    """
    if not templates:
        log.error("Jinja2 樣板引擎未初始化，無法渲染 file_item。")
        return '<div class="file-item" style="color: red;">錯誤：渲染引擎未就緒。</div>'

    try:
        template = templates.get_template("_processed_file_item.html")
        return template.render({"file": file_data})
    except Exception as e:
        log.error(f"渲染 _processed_file_item.html 失敗: {e}", exc_info=True)
        return f'<div class="file-item" style="color: red;">渲染錯誤: {e}</div>'
