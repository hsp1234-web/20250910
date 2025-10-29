# src/api/routes/line_data_api.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
import logging
import re

# --- 專案內部模組匯入 ---
from db.client import DBClient

# --- 日誌設定 ---
log = logging.getLogger('api_gateway')

# --- FastAPI 路由器 ---
router = APIRouter(
    prefix="/api/line_data",
    tags=["LINE Data Viewer"],
)

# --- 依賴注入 ---
def get_db_client():
    """提供一個 DBClient 的共享實例。"""
    return DBClient()

# --- 智慧排序輔助函式 ---
def natural_sort_key(s: str) -> list:
    """
    實現自然排序 (e.g., 'item2' comes before 'item10')。
    專為 '數字-名字' 的格式優化。
    """
    if s is None:
        return [float('inf'), '']
    # 嘗試用正則表達式匹配 '數字-名字' 的模式
    match = re.match(r'(\d+)-?(.*)', s)
    if match:
        # 如果匹配成功，回傳數字部分和文字部分
        return [int(match.group(1)), match.group(2).strip()]
    else:
        # 如果不匹配 (例如純文字)，將數字部分設為無窮大，使其排在後面
        return [float('inf'), s]

# --- API 端點 ---
@router.get("/items", summary="獲取所有 LINE 項目，並支援智慧排序")
async def get_all_line_items(
    sort_by: Optional[str] = Query('id', description="排序欄位"),
    sort_order: Optional[str] = Query('desc', description="排序順序 (asc/desc)"),
    db_client: DBClient = Depends(get_db_client)
):
    """
    從資料庫中獲取所有已匯入的 LINE 項目，並提供靈活的排序選項。
    """
    try:
        all_items = db_client.get_filtered_urls(source="line_importer") # 只獲取 LINE 匯入的項目
        if not all_items:
            return []

        # 執行排序
        reverse_order = sort_order.lower() == 'desc'

        if sort_by == 'author':
            # 如果是按作者排序，使用我們的智慧排序函式
            sorted_items = sorted(all_items, key=lambda item: natural_sort_key(item.get('author')), reverse=reverse_order)
        else:
            # 對於其他欄位，使用標準排序
            # 對於 None 值，我們將其視為最小值，以便在升序時排在最前面
            sorted_items = sorted(all_items, key=lambda item: (item.get(sort_by) is None, item.get(sort_by)), reverse=reverse_order)

        return sorted_items
    except Exception as e:
        log.error(f"從資料庫獲取 LINE 項目時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="無法從資料庫讀取項目清單。")

@router.get("/item/{item_id}", summary="獲取單一 LINE 項目的詳細資訊")
async def get_line_item_details(item_id: int, db_client: DBClient = Depends(get_db_client)):
    """
    根據 ID 獲取單個項目的所有詳細資料，用於編輯頁面。
    """
    try:
        item = db_client.get_url_by_id(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="找不到指定的項目。")
        return item
    except Exception as e:
        log.error(f"獲取項目 {item_id} 詳情時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="讀取項目詳情時發生錯誤。")

from pydantic import BaseModel

class ItemUpdate(BaseModel):
    extracted_text: Optional[str] = None
    ai_summary: Optional[str] = None

@router.put("/item/{item_id}", summary="更新單一 LINE 項目的詳細資訊")
async def update_line_item(
    item_id: int,
    update_data: ItemUpdate,
    db_client: DBClient = Depends(get_db_client)
):
    """
    更新指定項目的可編輯欄位，例如 extracted_text 和 ai_summary。
    """
    try:
        # Pydantic 的 model_dump(exclude_unset=True) 只會包含實際傳入的欄位
        updates = update_data.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(status_code=400, detail="請求中未包含任何要更新的資料。")

        success = db_client.update_url(item_id, updates)

        if not success:
            # 這可能是因為資料庫錯誤或找不到項目
            raise HTTPException(status_code=500, detail="更新資料庫時發生錯誤。")

        # 回傳更新後的完整項目
        updated_item = db_client.get_url_by_id(item_id)
        if not updated_item:
             raise HTTPException(status_code=404, detail="更新後找不到該項目。")

        return updated_item
    except HTTPException as e:
        raise e
    except Exception as e:
        log.error(f"更新項目 {item_id} 時發生錯誤: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新項目時發生伺服器內部錯誤。")