import pytest
import httpx
import sqlite3
import time
from pathlib import Path
from typing import List, Dict

# Test data from the previous test
# Using an ASCII-only author name to avoid framework-level path issues.
LINE_CHAT_LOG_FOR_SETUP = """
2025/4/4（週五）
17:46	504-0718103Leo	四月小作文-精確3162
https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0
17:48	505-0724540WOLF	四月小作文-5515建國
https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk
"""

def get_db_rows(db_path: str, table_name: str, where_clause: str = "1=1") -> List[Dict]:
    """Helper function to get rows from a table with a filter."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name} WHERE {where_clause}")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

@pytest.mark.e2e
def test_page2_download_flow(live_services):
    """
    Tests the full Page 2 flow against the real, now-fixed implementation.
    1. Sets up the DB with pending URLs by calling Page 1 API.
    2. Calls the Page 2 API to start the download.
    3. Polls the database until the status is updated.
    4. Verifies the final DB state and that the files were created.
    """
    base_url = live_services["base_url"]
    db_path = live_services["db_path"]

    # --- 0. Cleanup: Ensure a clean state for this test ---
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM extracted_urls")
    conn.execute("DELETE FROM analysis_tasks")
    conn.commit()
    conn.close()

    # --- 1. Setup: Ingest URLs using Page 1 API ---
    ingest_url = f"{base_url}/api/ingestion/extract_urls"
    payload = {"text": LINE_CHAT_LOG_FOR_SETUP}
    with httpx.Client() as client:
        response = client.post(ingest_url, json=payload)
        assert response.status_code == 200, f"API call failed: {response.text}"

    # Get the IDs of the pending URLs
    pending_urls = get_db_rows(db_path, "extracted_urls", "status = 'pending'")
    assert len(pending_urls) == 2
    ids_to_download = [url['id'] for url in pending_urls]

    # --- 2. Action: Start the download process ---
    download_url = f"{base_url}/api/downloader/start_downloads"
    download_payload = {"ids": ids_to_download}
    with httpx.Client() as client:
        response = client.post(download_url, json=download_payload)
        assert response.status_code == 200
        assert "已成功為 2 個項目建立背景下載任務" in response.json()["message"]

    # --- 3. Verification: Poll for completion ---
    completed_successfully = False
    # Increase timeout to allow for real network downloads
    for _ in range(120):  # Poll for up to 60 seconds
        completed_rows = get_db_rows(db_path, "extracted_urls", "status = 'completed'")
        if len(completed_rows) == 2:
            completed_successfully = True
            break
        time.sleep(0.5)

    assert completed_successfully, "Download tasks did not complete in time."

    # --- 4. Final Assertions ---
    final_rows = get_db_rows(db_path, "extracted_urls")
    for row in final_rows:
        assert row['id'] in ids_to_download
        assert row['status'] == 'completed'
        assert row['local_path'] is not None

        # Check that the file was actually created
        file_path = Path(row['local_path'])
        assert file_path.exists()
        assert file_path.stat().st_size > 0 # Check that it's not an empty file

        # Verify the filename convention
        filename = file_path.name
        assert str(row['id']) in filename
        assert "Leo" in filename or "WOLF" in filename
        assert "2025-04-04" in filename

        # Clean up the created file
        file_path.unlink()
