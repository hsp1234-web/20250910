import pytest
import sys
import sqlite3
import json
import os
import re
from pathlib import Path
from docx import Document
from docx.shared import Inches
from fpdf import FPDF
from PIL import Image
import gdown
import filetype

# --- 測試環境路徑設定 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 準備匯入被測試的模組 ---
from db.database import get_db_connection, initialize_database
from api.routes.page3_processor import run_processing_task

# --- Pytest Fixtures (測試輔助工具) ---

@pytest.fixture(scope="function")
def db_conn(tmp_path, monkeypatch):
    """
    提供一個乾淨的、初始化的、基於檔案的暫存 SQLite 資料庫。
    這個 fixture 會：
    1. 建立一個暫存資料庫檔案。
    2. 設定 TEST_DB_PATH 環境變數，讓 get_db_connection() 能找到它。
    3. 在此資料庫上執行初始化。
    4. 將連線物件提供給測試。
    5. 在測試結束後自動清理。
    """
    temp_db_path = tmp_path / "test_tasks.db"
    monkeypatch.setenv("TEST_DB_PATH", str(temp_db_path))

    # 現在 get_db_connection() 將會連線到我們的暫存資料庫
    # 我們也將這個連線傳遞給 initialize_database
    conn = get_db_connection()
    assert conn is not None, "無法建立到暫存資料庫的連線"

    initialize_database(conn)

    yield conn

    conn.close()
    # 檢查檔案是否存在，以防連線失敗
    if temp_db_path.exists():
        os.remove(temp_db_path)

@pytest.fixture(scope="module")
def dummy_image_path(tmpdir_factory):
    """建立一個用於測試的假圖片，並回傳其路徑。"""
    img = Image.new('RGB', (100, 100), color = 'blue')
    img_path = tmpdir_factory.mktemp("fixtures").join("dummy_image.png")
    img.save(str(img_path))
    return str(img_path)

def create_test_docx(dir_path, image_path):
    """輔助函式：建立一個測試用的 DOCX 檔案。"""
    doc = Document()
    doc.add_paragraph("這是DOCX文件。")
    doc.add_picture(image_path, width=Inches(1))
    file_path = Path(dir_path) / "test.docx"
    doc.save(file_path)
    return str(file_path)

def create_test_pdf(dir_path, image_path):
    """輔助函式：建立一個測試用的 PDF 檔案。"""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    # 使用英文以避免 FPDF 的 Unicode 字型問題，因為本測試的重點是檔案處理而非文字渲染
    pdf.cell(text="This is a PDF document.")
    # 將圖片置於文字下方
    pdf.image(image_path, x=10, y=20, w=50)
    file_path = Path(dir_path) / "test.pdf"
    pdf.output(file_path)
    return str(file_path)

# --- 整合測試案例 ---

@pytest.mark.parametrize(
    "file_creator, file_type",
    [
        (create_test_docx, "DOCX"),
        (create_test_pdf, "PDF"),
    ],
    ids=["process_docx_file", "process_pdf_file"]
)
def test_real_file_processing_task(db_conn, tmp_path, dummy_image_path, file_creator, file_type):
    """
    這是一個參數化的整合測試，用於驗證真實檔案（DOCX 和 PDF）的處理流程。
    """
    # 1. **準備**: 建立測試檔案並在資料庫中設定初始狀態
    # tmp_path 是 pytest 提供的每個測試函式專用的暫存目錄
    test_file_path = file_creator(tmp_path, dummy_image_path)

    cursor = db_conn.cursor()
    # 插入一筆模擬已下載完成的紀錄
    cursor.execute(
        "INSERT INTO extracted_urls (url, status, local_path) VALUES (?, ?, ?)",
        (f"http://test.com/test.{file_type.lower()}", "completed", test_file_path)
    )
    db_conn.commit()
    url_id = cursor.lastrowid
    assert url_id is not None

    # 2. **執行**: 呼叫背景任務函式來處理這個檔案
    # 我們在測試中同步執行它，並傳入一個假的埠號 (port=0)，因為我們不測試通知部分
    run_processing_task(url_id, port=0)

    # 3. **驗證**: 從資料庫中讀取結果並進行斷言
    cursor.execute("SELECT * FROM extracted_urls WHERE id = ?", (url_id,))
    result = cursor.fetchone()

    assert result is not None, "處理後的紀錄不應為 None"

    # 驗證狀態是否已更新
    assert result["status"] == "processed", f"{file_type} 檔案處理後狀態應為 'processed'"

    # 驗證檔案雜湊值是否已計算
    assert result["file_hash"] is not None, f"{file_type} 檔案應計算並儲存 file_hash"
    assert len(result["file_hash"]) == 64, "file_hash 應為 SHA256 的長度"

    # 驗證圖片是否已提取
    assert result["extracted_image_paths"] is not None, f"{file_type} 檔案應提取圖片路徑"

    try:
        extracted_images = json.loads(result["extracted_image_paths"])
        assert isinstance(extracted_images, list), "提取的圖片路徑應為一個列表"
        assert len(extracted_images) > 0, f"應從 {file_type} 檔案中提取出至少一張圖片"

        # 驗證提取出的圖片檔案確實存在
        extracted_image_path = Path(extracted_images[0])
        assert extracted_image_path.exists(), f"提取出的圖片檔案 {extracted_image_path} 應存在於檔案系統中"

    except (json.JSONDecodeError, IndexError):
        pytest.fail("extracted_image_paths 欄位不是一個有效的、包含路徑的 JSON 列表")

    # 驗證文字是否已提取
    assert result["extracted_text"] is not None, "extracted_text 欄位不應為 None"
    assert isinstance(result["extracted_text"], str), "extracted_text 應為字串"
    assert len(result["extracted_text"].strip()) > 0, "提取的文字內容不應為空"

    # 根據檔案類型檢查特定的文字內容
    if file_type == "DOCX":
        assert "這是DOCX文件" in result["extracted_text"]
    elif file_type == "PDF":
        # 注意：FPDF 在測試中可能不會輸出完全相同的文字，但我們可以檢查關鍵字
        assert "This is a PDF document" in result["extracted_text"]

    print(f"\n✅ {file_type} 檔案整合測試成功!")
    print(f"  - 狀態更新為: {result['status']}")
    print(f"  - 提取的圖片: {result['extracted_image_paths']}")
    print(f"  - 提取的文字 (前50字): {result['extracted_text'][:50]}...")


def test_drive_downloader_new_logic(tmp_path, monkeypatch):
    """
    測試 drive_downloader 是否能根據新邏輯正確處理檔案：
    - 使用 filetype 偵測副檔名
    - 使用傳入的 url_id 和 created_at 建立檔名
    """
    # 1. 準備
    fake_download_dir = tmp_path / "downloads"
    fake_download_dir.mkdir()

    # 模擬 filetype.guess 的回傳物件
    class MockFileType:
        extension = "pdf"
        mime = "application/pdf"

    # 2. Mock: 使用更穩健的方式模擬 gdown 的行為
    def mock_gdown_download(url, output, **kwargs):
        # 模擬 gdown 的核心行為：在指定的 output 路徑建立一個非空檔案
        with open(output, "w") as f:
            f.write("mock content")
        # 回傳該路徑，就像真實的 gdown 會做的一樣
        return output

    monkeypatch.setattr(gdown, "download", mock_gdown_download)
    monkeypatch.setattr("filetype.guess", lambda path: MockFileType())

    # 3. 執行
    from tools.drive_downloader import download_file
    url_id = 99
    created_at = "2025-01-01 10:30:00"

    final_path_str = download_file(
        url="http://fake.url/doc.pdf",
        output_dir=str(fake_download_dir),
        url_id=url_id,
        created_at_str=created_at
    )

    # 4. 驗證
    assert final_path_str is not None
    final_path = Path(final_path_str)

    # 驗證最終檔案存在
    assert final_path.exists()

    # 驗證檔名是否符合 'YYYY-MM-DDTHH-MM-SS_file_ID.ext' 格式
    expected_timestamp = "2025-01-01T10-30-00"
    expected_filename = f"{expected_timestamp}_file_{url_id}.pdf"
    assert final_path.name == expected_filename, f"檔名應為 {expected_filename}，但卻是 {final_path.name}"
