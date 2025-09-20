import logging
import sys
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import pandas as pd
from io import BytesIO

# --- 路徑修正與模組匯入 ---
SRC_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log
# V4 優化：移除舊的資料庫連線方式
# from db.database import get_db_connection
from fastapi import Depends
from db.client import DBClient
from ..dependencies import get_db

# --- 常數與設定 ---
log = logging.getLogger(__name__)
templates = Jinja2Templates(directory=str(SRC_DIR / "static"))
router = APIRouter()

class UrlExtractionRequest(BaseModel):
    text: str

# --- HTML 頁面路由 ---
@router.get("/page1/ingestion", response_class=HTMLResponse)
async def get_ingestion_page(request: Request):
    return templates.TemplateResponse("page1_sub_ingestion.html", {"request": request})

@router.get("/page1/overview", response_class=HTMLResponse)
async def get_overview_page(request: Request):
    return templates.TemplateResponse("page1_sub_overview.html", {"request": request})

@router.get("/page1/export", response_class=HTMLResponse)
async def get_export_page(request: Request):
    return templates.TemplateResponse("page1_sub_export.html", {"request": request})

# --- API 端點 ---
@router.post("/api/page1/extract_urls", status_code=200)
async def extract_urls_endpoint(payload: UrlExtractionRequest, db: DBClient = Depends(get_db)):
    """(V4 優化後) 提取 URL 並使用 DBClient 儲存。"""
    source_text = payload.text
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="提供的文字不可為空。")

    try:
        parsed_data = parse_chat_log(source_text)
        if parsed_data:
            # 使用新的 DBClient 方法
            db.add_new_urls(parsed_data, source_text)
        # 即使沒有新增資料，也回傳解析出的內容讓前端確認
        return JSONResponse(content=parsed_data)
    except Exception as e:
        log.error(f"處理網址提取請求時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/page1/overview_data")
async def get_overview_data(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    count_only: bool = Query(False),
    db: DBClient = Depends(get_db)
):
    """(V4 優化後) 使用 DBClient 獲取總覽資料。"""
    try:
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        if count_only:
            return {"count": len(results)}
        return JSONResponse(content=results)
    except Exception as e:
        log.error(f"查詢總覽資料時發生錯誤: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="資料庫查詢失敗")

from weasyprint import HTML
from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement

def add_hyperlink(paragraph, text, url):
    """
    在段落中新增一個超連結。
    :param paragraph: 要新增超連結的 `docx.text.paragraph.Paragraph` 物件。
    :param text: 超連結的顯示文字。
    :param url: 超連結的目標 URL。
    :return: 新增的 `docx.text.run.Run` 物件。
    """
    # 獲取文件 part
    part = paragraph.part
    # 建立一個唯一的關聯 ID (rId)
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    # 建立 <w:hyperlink> 元素
    hyperlink = OxmlElement('w:hyperlink')
    hyperlink.set(qn('r:id'), r_id)

    # 建立 <w:r> (Run) 元素
    new_run = OxmlElement('w:r')

    # 建立 <w:rPr> (Run Properties) 元素並設定樣式
    rPr = OxmlElement('w:rPr')
    rStyle = OxmlElement('w:rStyle')
    rStyle.set(qn('w:val'), 'Hyperlink') # 使用 Word 的內建超連結樣式
    rPr.append(rStyle)
    new_run.append(rPr)

    # 設定超連結的顯示文字
    new_run.text = text
    hyperlink.append(new_run)

    # 將超連結元素新增到段落中
    paragraph._p.append(hyperlink)

    return new_run

@router.get("/api/page1/export")
async def export_data(
    request: Request,
    format: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    style: str = Query('cards'), # 新增 style 參數
    db: DBClient = Depends(get_db)
):
    """
    (V38 效能優化) 使用 DBClient 獲取資料並根據指定格式匯出。
    - 更新 DOCX 匯出功能，使其包含所有欄位並支援超連結。
    - HTML/PDF 現在會顯示完整的卡片資訊。
    - 新增 HTML/PDF 的表格樣式選項，以應對大量資料匯出的效能問題。
    """
    try:
        # 獲取資料
        results = db.get_filtered_urls(start_date=start_date, end_date=end_date)
        # 組合日期和時間欄位
        for r in results:
            r['datetime_str'] = f"{r.get('message_date', '')} {r.get('message_time', '')}".strip()

    except Exception as e:
        log.error(f"匯出時讀取資料庫失敗: {e}", exc_info=True)
        if isinstance(e, (ConnectionError, RuntimeError)):
             raise HTTPException(status_code=503, detail=f"資料庫服務通訊失敗: {e}")
        raise HTTPException(status_code=500, detail="讀取資料庫失敗")

    # 根據匯出格式與樣式準備內容
    if format in ["html", "pdf"]:
        template_name = "export_table.html" if style == "table" else "export_cards.html"
        html_content = templates.TemplateResponse(
            template_name,
            {
                "request": request,
                "data": results,
                "start_date": start_date,
                "end_date": end_date
            }
        ).body.decode("utf-8")

        if format == "html":
            return Response(
                content=html_content,
                media_type="text/html",
                headers={"Content-Disposition": "attachment; filename=export.html"}
            )

        if format == "pdf":
            pdf_output = BytesIO()
            HTML(string=html_content).write_pdf(pdf_output)
            pdf_output.seek(0)
            return Response(
                pdf_output.read(),
                media_type="application/pdf",
                headers={"Content-Disposition": "attachment; filename=export.pdf"}
            )

    elif format == "excel":
        df = pd.DataFrame(results)
        # 重新排序與命名欄位以符合需求
        df_export = df[['id', 'title', 'author', 'datetime_str', 'status', 'url']]
        df_export.columns = ['ID', '標題', '作者', '時間', '狀態', '連結']

        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='資料匯出')
        output.seek(0)
        return Response(
            output.read(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=export.xlsx"}
        )
    elif format == "csv":
        df = pd.DataFrame(results)
        # 重新排序與命名欄位以符合需求
        df_export = df[['id', 'title', 'author', 'datetime_str', 'status', 'url']]
        df_export.columns = ['ID', '標題', '作者', '時間', '狀態', '連結']

        output = df_export.to_csv(index=False, encoding='utf-8-sig')
        return Response(
            content=output,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"}
        )
    elif format == "pdf":
        # V36.8: 實作 PDF 匯出
        html_content = templates.TemplateResponse(
            "export_cards.html",
            {
                "request": request,
                "data": results,
                "start_date": start_date,
                "end_date": end_date
            }
        ).body.decode("utf-8")

        pdf_output = BytesIO()
        # 使用 weasyprint 將 HTML 轉為 PDF，它會自動處理超連結
        HTML(string=html_content).write_pdf(pdf_output)
        pdf_output.seek(0)

        return Response(
            pdf_output.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=export.pdf"}
        )
    elif format == "docx":
        # V37.5: 全面改造 DOCX 匯出功能
        document = Document()
        document.add_heading('資料總覽報告', level=1)

        # 新增日期範圍資訊
        p = document.add_paragraph()
        p.add_run('篩選範圍: ').bold = True
        p.add_run(f"{start_date or '所有時間'} 至 {end_date or '所有時間'}")
        document.add_paragraph() # 新增一個間距

        # 建立包含所有欄位的表格
        table = document.add_table(rows=1, cols=6)
        table.style = 'Table Grid'
        table.autofit = True

        # 設定表頭
        hdr_cells = table.rows[0].cells
        headers = ['ID', '標題', '作者', '時間', '狀態', '連結']
        for i, header_text in enumerate(headers):
            hdr_cells[i].text = header_text
            # V37.5: 讓表頭文字自動換行
            hdr_cells[i].paragraphs[0].runs[0].font.bold = True

        # 填入資料
        for item in results:
            row_cells = table.add_row().cells
            row_cells[0].text = str(item.get('id', ''))
            row_cells[1].text = item.get('title', 'N/A')
            row_cells[2].text = item.get('author', 'N/A')
            row_cells[3].text = item.get('datetime_str', 'N/A')
            row_cells[4].text = item.get('status', 'N/A')

            # 新增超連結
            url = item.get('url')
            if url:
                # 清空儲存格預設段落
                cell_paragraph = row_cells[5].paragraphs[0]
                cell_paragraph.clear()
                add_hyperlink(cell_paragraph, url, url)

        # 儲存至記憶體
        output = BytesIO()
        document.save(output)
        output.seek(0)

        return Response(
            output.read(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": "attachment; filename=export.docx"}
        )
    else:
        # 對於不支援的格式，回傳錯誤
        raise HTTPException(status_code=400, detail=f"不支援的匯出格式: {format}")
