import os
import logging
import subprocess
import zipfile
import gdown
import glob
import base64
import html
from typing import Dict, Any

try:
    from weasyprint import HTML, CSS
except ImportError:
    logging.warning("WeasyPrint not found. PDF report generation will be disabled.")
    HTML, CSS = None, None

def setup_font() -> bool:
    """
    檢查並安裝 Noto Sans TC 字體，以確保 PDF 中的中文能正確顯示。
    """
    font_path = '/usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf'
    if os.path.exists(font_path):
        logging.info(f"✅ 中文字體已存在於: {font_path}")
        return True
    logging.info("⏳ 中文字體未找到，開始執行安裝程序...")
    font_zip_path, gdrive_id = "/tmp/noto_sans_tc.zip", '1NKofD5jLOI762WNvCdJNpmZQoJ5D95mG'
    try:
        gdown.download(id=gdrive_id, output=font_zip_path, quiet=False)
        extract_path = '/tmp/noto_font_extracted'
        if os.path.exists(extract_path): subprocess.run(['rm', '-rf', extract_path], check=True)
        os.makedirs(extract_path)
        with zipfile.ZipFile(font_zip_path, 'r') as zf: zf.extractall(extract_path)
        found_font = next(iter(glob.glob(os.path.join(extract_path, '**', 'NotoSansTC-Regular.ttf'), recursive=True)), None)
        if not found_font: raise FileNotFoundError("在解壓縮的檔案中找不到 'NotoSansTC-Regular.ttf'")
        target_dir = os.path.dirname(font_path)
        subprocess.run(['sudo', 'mkdir', '-p', target_dir], check=True)
        subprocess.run(['sudo', 'cp', found_font, font_path], check=True)
        subprocess.run(['sudo', 'fc-cache', '-f', '-v'], capture_output=True)
        logging.info(f"✅ 字體成功安裝至: {font_path}")
        return True
    except Exception as e:
        logging.error(f"❌ 字體安裝過程中發生錯誤: {e}")
        return False

def generate_final_report(report_data: Dict[str, Any], output_pdf_path: str) -> bool:
    """
    根據分析後的資料，生成一份圖文並茂的 PDF 報告。
    - report_data: 包含原始內容和 AI 分析結果的字典。
    - output_pdf_path: 最終 PDF 報告的儲存路徑。
    """
    if not HTML or not CSS:
        logging.error("無法生成 PDF 報告，因為 WeasyPrint 模組未安裝。")
        return False
    logging.info(f"準備生成 PDF 報告至: {output_pdf_path}")
    text_content = report_data.get("original_content", {}).get("text", "")
    image_paths = report_data.get("original_content", {}).get("image_paths", [])
    text_analysis = report_data.get("ai_analysis", {}).get("text_analysis", {})
    image_analyses = report_data.get("ai_analysis", {}).get("image_analyses", [])

    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in text_content.split('\\n') if p.strip())

    summary_html = f"<h3>AI 文字摘要</h3><p>{html.escape(text_analysis.get('summary', '無'))}</p>"
    keywords_html = f"<h3>AI 關鍵字</h3><p>{', '.join(text_analysis.get('keywords', []))}</p>"

    charts_html = ""
    img_analysis_map = {list(item.keys())[0]: list(item.values())[0] for item in image_analyses}
    for img_path in image_paths:
        try:
            with open(img_path, 'rb') as f: img_b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(img_path)[1].lstrip('.')
            desc = img_analysis_map.get(img_path, {}).get('description', '無可用描述')
            charts_html += f"<div class='chart-item'><img src='data:image/{ext};base64,{img_b64}'><p><b>AI 描述:</b> {html.escape(desc)}</p></div>"
        except Exception as e:
            charts_html += f"<p>圖片 '{os.path.basename(img_path)}' 載入失敗: {e}</p>"

    font_css = """@font-face {font-family: 'Noto Sans TC'; src: url('file:///usr/share/fonts/truetype/noto/NotoSansTC-Regular.ttf');} body {font-family: 'Noto Sans TC', sans-serif; line-height: 1.6;} .chart-item img {max-width: 80%; display: block; margin: 20px auto; border: 1px solid #ccc;} .chart-item p {text-align: center; margin-top: 5px;}"""
    html_template = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><title>分析報告</title></head><body><h1>分析報告</h1><h2>AI 分析結果</h2>{summary_html}{keywords_html}<hr><h2>原始文字內容</h2>{paragraphs}<hr><h2>圖片內容</h2>{charts_html}</body></html>"""

    try:
        HTML(string=html_template).write_pdf(output_pdf_path, stylesheets=[CSS(string=font_css)])
        logging.info(f"✅ PDF 報告成功生成於: {output_pdf_path}")
        return True
    except Exception as e:
        logging.error(f"❌ 使用 WeasyPrint 生成 PDF 時發生錯誤: {e}")
        return False

def generate_html_report_from_data(report_data: Dict[str, Any], title: str = "分析報告") -> str:
    """
    根據分析後的資料，生成一份圖文並茂的 HTML 報告字串。
    - report_data: 包含原始內容和 AI 分析結果的字典。
    - title: 報告的標題。
    """
    logging.info(f"準備生成標題為 '{title}' 的 HTML 報告...")

    # 從 report_data 解構所需內容
    text_content = report_data.get("original_content", {}).get("text", "")
    image_paths = report_data.get("original_content", {}).get("image_paths", [])
    text_analysis = report_data.get("ai_analysis", {}).get("text_analysis", {})
    image_analyses = report_data.get("ai_analysis", {}).get("image_analyses", [])

    # 處理原始文字段落
    paragraphs = "".join(f"<p>{html.escape(p)}</p>" for p in text_content.split('\\n') if p.strip())

    # 處理 AI 分析結果
    summary_html = f"<h3>AI 文字摘要</h3><p>{html.escape(text_analysis.get('summary', '無'))}</p>"
    keywords_html = f"<h3>AI 關鍵字</h3><p>{', '.join(text_analysis.get('keywords', []))}</p>"

    # 處理圖片和圖片的 AI 描述
    charts_html = ""
    # 將圖片分析列表轉換為更容易查詢的字典
    img_analysis_map = {list(item.keys())[0]: list(item.values())[0] for item in image_analyses}
    for img_path in image_paths:
        try:
            # 為了讓 HTML 檔案能獨立顯示圖片，我們將圖片轉換為 Base64 內嵌進 HTML
            with open(img_path, 'rb') as f:
                img_b64 = base64.b64encode(f.read()).decode()
            ext = os.path.splitext(img_path)[1].lstrip('.')
            desc = img_analysis_map.get(img_path, {}).get('description', '無可用描述')

            charts_html += f"""
            <div class='chart-item'>
                <img src='data:image/{ext};base64,{img_b64}' alt='{html.escape(os.path.basename(img_path))}'>
                <p><b>AI 描述:</b> {html.escape(desc)}</p>
            </div>
            """
        except Exception as e:
            charts_html += f"<p>圖片 '{os.path.basename(img_path)}' 載入失敗: {e}</p>"

    # 組裝完整的 HTML
    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <title>{html.escape(title)}</title>
        <style>
            body {{ font-family: sans-serif; line-height: 1.6; margin: 20px; }}
            .chart-item img {{ max-width: 90%; display: block; margin: 20px auto; border: 1px solid #ccc; padding: 5px; }}
            .chart-item p {{ text-align: center; margin-top: 5px; font-style: italic; }}
            hr {{ margin: 40px 0; }}
        </style>
    </head>
    <body>
        <h1>{html.escape(title)}</h1>
        <h2>AI 分析結果</h2>
        {summary_html}
        {keywords_html}
        <hr>
        <h2>圖片內容</h2>
        {charts_html}
        <hr>
        <h2>原始文字內容</h2>
        {paragraphs}
    </body>
    </html>
    """

    logging.info("✅ HTML 報告內容成功生成。")
    return html_template
