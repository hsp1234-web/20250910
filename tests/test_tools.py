import pytest
import sys
from pathlib import Path
from docx import Document
from docx.shared import Inches
from PIL import Image
import os

# --- 測試環境路徑設定 ---
# 確保測試程式可以找到 src 目錄下的模組
# 雖然 pytest.ini 已設定，但在某些執行環境下顯式加入更為保險
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 準備匯入被測試的模組 ---
# 這些是我們想要測試的核心工具
from tools.content_extractor import extract_content
from tools.image_compressor import compress_image

# --- Pytest Fixtures (測試輔助工具) ---

@pytest.fixture(scope="module")
def temp_test_dir(tmpdir_factory):
    """
    建立一個專供本模組所有測試使用的暫存目錄。
    'scope="module"' 表示此目錄在所有測試執行前只會建立一次。
    """
    # 使用 pytest 內建的 tmpdir_factory 來建立一個唯一的暫存目錄
    return tmpdir_factory.mktemp("test_tools_data")

@pytest.fixture(scope="module")
def dummy_image_path(temp_test_dir):
    """
    在暫存目錄中建立一個用於測試的假圖片，並回傳其路徑。
    """
    # 建立一個 100x100 的紅色正方形圖片
    img = Image.new('RGB', (100, 100), color = 'red')
    img_path = Path(temp_test_dir) / "dummy_image.png"
    img.save(img_path)
    return str(img_path)

@pytest.fixture(scope="module")
def simulated_docx_path(temp_test_dir, dummy_image_path):
    """
    在暫存目錄中建立一個包含文字和圖片的假 .docx 檔案。
    """
    document = Document()
    document.add_heading('測試文件標題', 0)

    p = document.add_paragraph('這是一個測試段落，用於模擬文件中的文字內容。')
    p.add_run('這是粗體字').bold = True
    p.add_run('，而這是斜體字。').italic = True

    document.add_paragraph('接下來是一張圖片：')
    # 將我們建立的假圖片加入文件中
    document.add_picture(dummy_image_path, width=Inches(1.25))

    docx_path = Path(temp_test_dir) / "simulated_document.docx"
    document.save(str(docx_path))
    return str(docx_path)

# --- 測試案例 ---

def test_file_processing_pipeline_simulation(simulated_docx_path, temp_test_dir):
    """
    這是一個完整的模擬測試案例，用於驗證從內容提取到圖片壓縮的整個流程。
    它使用了上面定義的 fixtures 來取得一個動態生成的 DOCX 檔案。
    """
    # --- 第一階段：驗證內容提取 (extract_content) ---

    # 1. **準備**: 定義提取出的圖片要儲存的目錄
    image_output_dir = Path(temp_test_dir) / "extracted_images"
    image_output_dir.mkdir()

    # 2. **執行**: 呼叫我們要測試的核心函式
    extraction_result = extract_content(simulated_docx_path, str(image_output_dir))

    # 3. **驗證**:
    # 檢查函式是否回傳了包含圖片路徑的字典
    assert extraction_result is not None, "內容提取函式不應回傳 None"
    assert "image_paths" in extraction_result, "提取結果應包含 'image_paths' 鍵"

    image_paths = extraction_result["image_paths"]
    # 檢查是否成功提取了一張圖片
    assert isinstance(image_paths, list), "圖片路徑應為一個列表"
    assert len(image_paths) == 1, "應從文件中提取出一張圖片"

    extracted_image_path_str = image_paths[0]
    extracted_image_path = Path(extracted_image_path_str)

    # 檢查提取出的圖片檔案是否真的存在於檔案系統中
    assert extracted_image_path.exists(), f"提取出的圖片檔案不存在於: {extracted_image_path}"
    # 檢查檔案是否在我們指定的輸出目錄中
    assert image_output_dir in extracted_image_path.parents, "提取出的圖片未儲存在指定的目錄"

    # --- 第二階段：驗證圖片壓縮 (compress_image) ---

    # 1. **準備**: 定義壓縮後圖片的儲存目錄
    compressed_output_dir = Path(temp_test_dir) / "compressed_images"
    compressed_output_dir.mkdir()

    # 2. **執行**: 將第一階段提取出的圖片路徑，傳遞給壓縮函式
    compressed_path_str = compress_image(str(extracted_image_path), str(compressed_output_dir))

    # 3. **驗證**:
    # 檢查函式是否回傳了有效的路徑
    assert compressed_path_str is not None, "圖片壓縮函式不應回傳 None"

    compressed_path = Path(compressed_path_str)
    # 檢查壓縮後的檔案是否真的存在
    assert compressed_path.exists(), f"壓縮後的圖片檔案不存在於: {compressed_path}"
    # 檢查壓縮後的檔案是否在我們指定的輸出目錄中
    assert compressed_output_dir in compressed_path.parents

    # 檢查壓縮是否有效（壓縮後的檔案大小應小於或等於原始檔案）
    original_size = extracted_image_path.stat().st_size
    compressed_size = compressed_path.stat().st_size
    assert compressed_size <= original_size, "壓縮後的圖片大小應小於或等於原始圖片"
    assert compressed_size > 0, "壓縮後的圖片檔案不應為空"

    print(f"\n✅ 模擬測試成功!")
    print(f"  - 原始 DOCX: {simulated_docx_path}")
    print(f"  - 提取的圖片: {extracted_image_path} (大小: {original_size} 位元組)")
    print(f"  - 壓縮後圖片: {compressed_path} (大小: {compressed_size} 位元組)")


# --- JULES-ADD-26.22-TEST: 為 gemini_processor.py 的 CLI 新增測試 ---
# 匯入我們要測試的目標模組和函式
from tools import gemini_processor
import asyncio
from unittest.mock import MagicMock

# 為了避免在測試中真的去呼叫耗時的網路或檔案處理，我們使用 mock
@pytest.mark.asyncio
async def test_gemini_processor_cli(monkeypatch, capsys, temp_test_dir):
    """
    測試 gemini_processor.py 的命令列介面 (CLI)。
    - 使用 monkeypatch 來模擬 sys.argv 和外部函式。
    - 使用 capsys 來捕獲標準輸出/錯誤。
    """
    # 1. 模擬 (Mock) 會產生外部效應的函式
    # 我們不希望測試真的去呼叫 Google API 或執行轉錄
    monkeypatch.setattr(gemini_processor, '_validate_key', lambda api_key: True)
    monkeypatch.setattr(gemini_processor, '_list_models', lambda api_key: [{"id": "mock-model", "name": "Mock Model"}])

    # JULES-FIX-26.22-TEST-Hotfix: 採用更穩健的 Mock 策略
    # 直接模擬整個 Transcriber 類別，而不是其方法，以避免因條件式匯入造成的 NoneType 錯誤
    mock_transcriber_instance = MagicMock()
    # 讓 .transcribe() 方法回傳一個固定的字串
    mock_transcriber_instance.transcribe.return_value = "這是模擬的逐字稿。"
    # 當 gemini_processor.py 試圖 `Transcriber(...)` 時，讓它回傳我們的模擬實例
    monkeypatch.setattr(gemini_processor, 'Transcriber', lambda *args, **kwargs: mock_transcriber_instance)

    # 模擬報告生成函式
    monkeypatch.setattr(gemini_processor, '_generate_report_from_transcript', lambda *args, **kwargs: "這是模擬的報告。")


    # 2. 測試 'validate_key' 指令
    monkeypatch.setattr(sys, 'argv', ['gemini_processor.py', '--command=validate_key', '--api-key=DUMMY_KEY'])
    with pytest.raises(SystemExit) as e:
        await gemini_processor.main()
    assert e.value.code == 0 # 驗證程式是否以成功狀態碼 0 退出
    captured = capsys.readouterr()
    assert "金鑰驗證成功" in captured.out


    # 3. 測試 'list_models' 指令
    monkeypatch.setattr(sys, 'argv', ['gemini_processor.py', '--command=list_models', '--api-key=DUMMY_KEY'])
    with pytest.raises(SystemExit) as e:
        await gemini_processor.main()
    assert e.value.code == 0
    captured = capsys.readouterr()
    # 驗證輸出是否為我們模擬的 JSON
    assert '{"id": "mock-model", "name": "Mock Model"}' in captured.out


    # 4. 測試 'process' 指令 - 缺少必要參數
    monkeypatch.setattr(sys, 'argv', ['gemini_processor.py', '--command=process']) # 故意不提供 --audio-file
    with pytest.raises(SystemExit) as e:
        await gemini_processor.main()
    assert e.value.code == 1 # 應以失敗狀態碼 1 退出
    captured = capsys.readouterr()
    assert "audio_file is required" in captured.err # 錯誤訊息應輸出到 stderr


    # 5. 測試 'process' 指令 - 成功執行
    # 我們需要一個假的音訊檔案路徑
    dummy_audio_path = Path(temp_test_dir) / "dummy.mp3"
    dummy_audio_path.touch() # 建立一個空檔案即可

    monkeypatch.setattr(sys, 'argv', [
        'gemini_processor.py',
        '--command=process',
        f'--audio-file={dummy_audio_path}',
        '--api-key=DUMMY_KEY'
        # 其他參數使用預設值
    ])
    with pytest.raises(SystemExit) as e:
        await gemini_processor.main()
    assert e.value.code == 0 # 應以成功狀態碼 0 退出
    captured = capsys.readouterr()
    # 驗證最終的成功 JSON 輸出
    assert '"status": "success"' in captured.out
    assert f'"transcript_path":' in captured.out
