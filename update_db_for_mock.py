import sys
from pathlib import Path
import sqlite3

# --- Path Correction ---
SRC_DIR = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SRC_DIR))

from db.database import get_db_connection

def update_db_for_mock_files():
    """
    Updates the database to link extracted URLs to the mock files.
    """
    db_path = SRC_DIR / "db" / "tasks.db"
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        return

    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get the IDs of the most recently added URLs that don't have a local_path yet.
        cursor.execute("SELECT id FROM extracted_urls WHERE local_path IS NULL ORDER BY id DESC LIMIT 2")
        rows = cursor.fetchall()
        if len(rows) < 2:
            print(f"Error: Not enough URLs without a local_path found to mock. Found {len(rows)}.")
            return

        url_ids = [row['id'] for row in rows]
        mock_files = [
            str(Path.cwd() / "downloads" / "mock_file_1.txt"),
            str(Path.cwd() / "downloads" / "mock_file_2.docx")
        ]

        print(f"Found pending URL IDs: {url_ids}")
        print("Will update them with mock file paths...")

        # Update the status and local_path for these URLs
        for i in range(len(url_ids)):
            url_id = url_ids[i]
            mock_file_path = mock_files[i]
            cursor.execute(
                """
                UPDATE extracted_urls
                SET status = 'downloaded', local_path = ?, status_message = 'Mocked Download'
                WHERE id = ?
                """,
                (mock_file_path, url_id)
            )
            print(f"Updated URL ID {url_id} with path {mock_file_path}")

        conn.commit()
        print("\nDatabase updated successfully.")

    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    update_db_for_mock_files()
