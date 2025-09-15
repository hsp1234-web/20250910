import pytest
import asyncio
import json
from pathlib import Path

# --- 測試環境路徑設定 ---
import sys
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# --- 模組匯入 ---
from api.routes.page4_analyzer import _run_stage1_blocking_task
from tests.conftest import db_conn  # Import fixture for type hinting and reuse if needed

# --- 常數 ---
MODEL_NAME = "gemini-1.5-flash-latest"
TEMP_JSON_DIR = Path(__file__).resolve().parent.parent / "temp_json"

def test_yfinance_integration(db_conn, monkeypatch):
    """
    整合測試：驗證 _run_stage1_blocking_task 是否能成功整合 yfinance 分析。
    """
    # 1. --- 準備 (Arrange) ---

    # Mock a successful Gemini API call that returns a stock symbol
    mock_ai_output = {
        "title": "台積電分析報告",
        "symbol": "2330.TW",
        "sentiment": "看多",
        "summary": "AI 晶片需求強勁，台積電前景看好。"
    }

    # Mock the GeminiManager to avoid real API calls
    class MockGeminiManager:
        def __init__(self, *args, **kwargs):
            pass
        def prompt_for_json(self, *args, **kwargs):
            # Return the predefined output, no error, a fake key name, and fake token usage
            return mock_ai_output, None, "mock_key", 100

    monkeypatch.setattr("api.routes.page4_analyzer.GeminiManager", MockGeminiManager)

    # JULES (2025-09-14): To solve ConnectionRefusedError, we replace the real
    # DBClient with a fake one that interacts directly with our test db_conn.
    class FakeDBClient:
        def __init__(self, conn):
            self._conn = conn
        def get_url_by_id(self, url_id):
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM extracted_urls WHERE id = ?", (url_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        def get_analysis_task(self, task_id):
            cursor = self._conn.cursor()
            cursor.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        def update_analysis_task(self, task_id, updates):
            set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
            values = list(updates.values()) + [task_id]
            sql = f"UPDATE analysis_tasks SET {set_clause} WHERE id = ?"
            self._conn.execute(sql, values)
            self._conn.commit()
            return True

    monkeypatch.setattr("api.routes.page4_analyzer.DB_CLIENT", FakeDBClient(db_conn))

    # Prepare the database with necessary data
    mock_file_id = 1
    mock_start_date = "2023-01-01"
    mock_text_content = "這是關於台積電(2330.TW)的分析文章。"

    cursor = db_conn.cursor()
    # Insert a record into extracted_urls to be looked up
    cursor.execute(
        "INSERT INTO extracted_urls (id, url, message_date) VALUES (?, ?, ?)",
        (mock_file_id, "http://mock.url/test", mock_start_date)
    )
    # Insert a corresponding analysis_task
    cursor.execute(
        "INSERT INTO analysis_tasks (file_id, filename, stage1_status, file_content_for_analysis) VALUES (?, ?, ?, ?)",
        (mock_file_id, "test.txt", 'pending', mock_text_content)
    )
    db_conn.commit()
    task_id = cursor.lastrowid
    assert task_id is not None

    # 2. --- 執行 (Act) ---
    mock_queue = asyncio.Queue()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    _run_stage1_blocking_task(
        task_id=task_id,
        file_id=mock_file_id,
        model_name=MODEL_NAME,
        queue=mock_queue,
        loop=loop
    )

    # 3. --- 驗證 (Assert) ---

    # Verify the database state
    cursor.execute("SELECT * FROM analysis_tasks WHERE id = ?", (task_id,))
    updated_task = dict(cursor.fetchone())

    assert updated_task is not None
    assert updated_task['stage1_status'] == 'completed'
    assert updated_task['stage1_json_path'] is not None

    # Verify the content of the created JSON file
    json_path = Path(updated_task['stage1_json_path'])
    assert json_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        final_data = json.load(f)

    # Check that AI data is preserved
    assert final_data['symbol'] == "2330.TW"

    # Check that quantitative analysis data was added
    assert "quantitative_analysis" in final_data
    qa_data = final_data["quantitative_analysis"]

    # Check for the expected metrics
    expected_keys = [
        "total_return", "annualized_return", "annualized_volatility",
        "max_drawdown", "sharpe_ratio", "alpha", "beta"
    ]
    for key in expected_keys:
        assert key in qa_data
        # Allow for None values, which can happen if data is insufficient for a metric
        assert isinstance(qa_data[key], (int, float)) or qa_data[key] is None

    # Clean up the created file
    json_path.unlink()
