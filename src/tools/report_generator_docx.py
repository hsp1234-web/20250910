# --- 檔案: src/tools/report_generator_docx.py ---
# --- 說明: 提供生成 .docx 格式績效報告的功能。---

import os
import logging
import json
from pathlib import Path
from typing import List

# 修正匯入路徑
try:
    from db.client import DBClient
except ImportError:
    # 如果直接執行此腳本，可能需要手動調整 sys.path
    import sys
    SRC_DIR = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(SRC_DIR))
    from db.client import DBClient


log = logging.getLogger(__name__)

# --- 核心函式 ---

def create_docx_report(task_ids: List[int], db_client: DBClient) -> str:
    """
    根據提供的任務 ID 列表，生成一份綜合的 Word (.docx) 報告。

    Args:
        task_ids: 一個包含分析任務 ID 的整數列表。
        db_client: 用於查詢資料庫的 DBClient 實例。

    Returns:
        生成後 .docx 檔案的絕對路徑。
    """
    from docx import Document
    from docx.shared import Inches

    log.info(f"開始為任務 {task_ids} 生成 Word 報告...")

    # --- 1. 創建 Word 文件 ---
    document = Document()
    document.add_heading('綜合績效分析報告', level=1)

    # --- 2. 迭代處理每個任務 ---
    for task_id in task_ids:
        task_data = db_client.get_analysis_task(task_id=task_id)
        if not task_data:
            log.warning(f"找不到任務 {task_id} 的資料，已跳過。")
            document.add_paragraph(f"找不到任務 ID: {task_id} 的分析資料。")
            continue

        document.add_heading(f"分析報告: {task_data.get('filename', '未知檔案')}", level=2)

        # --- 3. 讀取並整合資料 ---
        json_path_str = task_data.get("stage1_json_path")
        if not json_path_str or not Path(json_path_str).exists():
            log.warning(f"任務 {task_id} 的 JSON 檔案路徑不存在或遺失。")
            document.add_paragraph("錯誤：找不到分析結果的 JSON 檔案。")
            continue

        with open(json_path_str, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        # --- 4. 填充文字和表格內容 ---
        add_report_content_to_document(document, report_data)

        # --- 5. 生成並插入圖表 ---
        # 暫時使用 PoC 的靜態圖表邏輯
        chart_path = generate_placeholder_chart()
        document.add_picture(chart_path, width=Inches(6.0))
        os.remove(chart_path) # 插入後刪除暫存圖檔

        document.add_page_break()

    # --- 6. 儲存最終文件 ---
    # 將報告儲存到一個暫存目錄，例如專案根目錄下的 'reports'
    REPORTS_DIR = Path(__file__).resolve().parent.parent.parent / "reports"
    REPORTS_DIR.mkdir(exist_ok=True)

    output_filename = f"generated_report_{task_ids[0]}.docx"
    output_path = REPORTS_DIR / output_filename

    document.save(output_path)
    log.info(f"Word 報告已成功儲存至: {output_path}")

    return str(output_path)


def add_report_content_to_document(document: Document, data: dict):
    """將單份報告的內容添加到 Word 文件中。"""

    # 建立一個表格顯示摘要資訊
    table = document.add_table(rows=1, cols=2)
    table.style = 'Table Grid'
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = '項目'
    hdr_cells[1].text = '內容'

    summary_data = {
        "分析標的": data.get("symbol", "N/A"),
        "公司名稱": data.get("company_name", "N/A"),
        "報告類型": data.get("report_type", "N/A"),
        "分析師": data.get("analyst", "N/A"),
        "目標價": str(data.get("target_price", "N/A")),
        "評級": data.get("rating", "N/A"),
    }

    for key, value in summary_data.items():
        row_cells = table.add_row().cells
        row_cells[0].text = key
        row_cells[1].text = value

    document.add_heading('詳細分析摘要', level=3)
    document.add_paragraph(data.get("summary", "沒有提供摘要。"))

    # 添加績效分析數據
    performance = data.get("performance_analysis", {})
    if performance:
        document.add_heading('量化績效分析', level=3)
        perf_table = document.add_table(rows=1, cols=2)
        perf_table.style = 'Table Grid'
        perf_hdr_cells = perf_table.rows[0].cells
        perf_hdr_cells[0].text = '績效指標'
        perf_hdr_cells[1].text = '數值'

        for key, value in performance.items():
            if key != 'chart_data': # 不顯示圖表原始數據
                row_cells = perf_table.add_row().cells
                row_cells[0].text = str(key)
                row_cells[1].text = str(value)


def generate_placeholder_chart() -> str:
    """
    生成一個佔位的 Plotly 圖表並回傳其路徑。
    (此為 PoC 邏輯的臨時版本)
    """
    import plotly.graph_objects as go
    fig = go.Figure(data=go.Scatter(x=[1, 2, 3, 4], y=[10, 11, 12, 13], mode='markers+lines'))
    fig.update_layout(title_text="範例績效圖表")

    chart_path = Path(__file__).resolve().parent / "temp_chart.png"
    fig.write_image(chart_path, engine="kaleido")
    return str(chart_path)

# --- 用於獨立測試的進入點 ---
if __name__ == '__main__':
    # 這段程式碼只在直接執行此檔案時運行
    print("正在以獨立模式測試報告生成器...")

    # 建立一個模擬的 DBClient
    class MockDBClient:
        def get_analysis_task(self, task_id):
            # 模擬從資料庫獲取資料
            # 實際測試時，需要確保這個 JSON 檔案存在
            poc_json_path = Path(__file__).resolve().parent.parent.parent / "temp_json" / "stage1_1_a97e0138.json"
            if not poc_json_path.exists():
                print(f"錯誤: 找不到測試用的 JSON 檔案: {poc_json_path}")
                # 建立一個假的
                fake_data = {
                    "symbol": "MOCK.TW", "company_name": "模擬公司", "report_type": "初評",
                    "analyst": "模擬分析師", "target_price": 100, "rating": "買進",
                    "summary": "這是一個模擬的摘要。",
                    "performance_analysis": {"+1d": 0.01, "+5d": -0.02}
                }
                with open(poc_json_path, "w", encoding="utf-8") as f:
                    json.dump(fake_data, f)
                print(f"已建立假的 JSON 檔案於: {poc_json_path}")


            return {
                "id": task_id,
                "filename": f"模擬檔案_{task_id}.txt",
                "stage1_json_path": str(poc_json_path)
            }

    mock_db = MockDBClient()

    # 執行生成報告的函式
    # 假設我們要為任務 ID 1 和 2 生成報告
    generated_file = create_docx_report(task_ids=[1, 2], db_client=mock_db)

    print(f"測試報告已生成於: {generated_file}")
